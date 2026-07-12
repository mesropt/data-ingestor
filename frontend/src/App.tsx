import { useEffect, useReducer, useState } from "react";
import { toast } from "sonner";

import { AppShell, type AppTab } from "@/components/AppShell";
import { SignedInIndicator } from "@/components/SignedInIndicator";
import { SignInRequiredGate } from "@/components/SignInRequiredGate";
import { SignInScreen } from "@/components/SignInScreen";
import { SignUpScreen } from "@/components/SignUpScreen";
import { VerifyLanding } from "@/components/VerifyLanding";
import { Toaster } from "@/components/ui/sonner";
import { Documentation } from "@/screens/Documentation";
import { Review } from "@/screens/Review";
import { Schemas } from "@/screens/Schemas";
import { Upload } from "@/screens/Upload";
import { getAuthConfig, getMe, signOut } from "@/lib/api";
import type { AuthUser, FieldSetPayload, MappingResponse } from "@/lib/types";
import { authReducer, initialAuthState, isSignedIn, isVerified } from "@/state/auth";
import { pathForTab, tabFromPath } from "@/state/routing";

// D-10-09: Define Fields is deleted, Registry is renamed to Schemas -- the
// tab shell shrinks from five slugs to four. TABS is the single source of
// truth for them -- this is the only other place they are listed, and it is
// a derived view (map), not a second copy.
const TABS: AppTab[] = [
  { value: "schemas", label: "Schemas" },
  { value: "upload", label: "Upload" },
  { value: "review", label: "Review" },
  { value: "docs", label: "Docs" },
];

// A bookmark for either deleted page's old path is no longer a TAB_VALUES
// member, so tabFromPath's existing allowlist fallback (state/routing.ts,
// byte unchanged by this plan) resolves it to TAB_VALUES[0] ("schemas") --
// the SAME mechanism that already resolves any garbage path today. Zero new
// code needed here (T-10-29, proven by state/routing.test.ts).
const TAB_VALUES = TABS.map((tab) => tab.value);

type AuthView = "signin" | "signup" | null;

/** The pending post-sign-in destination the store carried while signed out
 * (stamped by SET_RETURN_TO from the ConfirmGate "Sign In to Confirm" flow). */
function pendingReturnTo(state: ReturnType<typeof authReducer>): string | undefined {
  return "returnTo" in state ? state.returnTo : undefined;
}

function App() {
  // ONE pathname state is the single source of truth for the URL; activeTab
  // (below) is DERIVED from it, never a second state. Tabs and /verify now
  // share one path axis, so two states over that axis is exactly the bug to
  // avoid -- they could disagree (e.g. pathname === "/review" while a
  // separate activeTab state still said "upload"). Seeded from the URL on
  // mount so a fresh load or F5 reopens whichever path the browser names.
  const [pathname, setPathname] = useState<string>(() =>
    typeof window === "undefined" ? "/" : window.location.pathname
  );
  // Derived, not state: tabFromPath's allowlist guarantees a valid
  // TAB_VALUES member even for a garbage path, so this can never resolve to
  // a blank screen, and it has no setter of its own -- it cannot drift out
  // of sync with pathname.
  const activeTab = tabFromPath(pathname, TAB_VALUES);
  const [lastMapping, setLastMapping] = useState<MappingResponse | null>(null);
  const [lastFieldSet, setLastFieldSet] = useState<FieldSetPayload | null>(null);

  const [authState, dispatch] = useReducer(authReducer, initialAuthState);
  const [googleEnabled, setGoogleEnabled] = useState(false);
  const [authView, setAuthView] = useState<AuthView>(null);

  // Mount-time session probe: learn the Google flag and resolve who (if
  // anyone) is signed in. A 401/ApiError from /api/auth/me means "signed out".
  useEffect(() => {
    getAuthConfig()
      .then((config) => setGoogleEnabled(config.google_oauth_enabled))
      .catch(() => setGoogleEnabled(false));
    getMe()
      .then((user) => dispatch({ type: "SESSION_RESOLVED", user }))
      .catch(() => dispatch({ type: "SESSION_RESOLVED", user: null }));
  }, []);

  // Back/Forward support: popstate fires ONLY for real browser Back/Forward
  // navigation, never for our own pushState calls below -- so there is no
  // self-fire to reason about at all. Clearing authView matters here for
  // the same reason it matters in navigateTo: pressing Back with the
  // sign-in overlay open must not swap the screen underneath a still-
  // covering overlay.
  useEffect(() => {
    function handlePopState() {
      setAuthView(null);
      setPathname(window.location.pathname);
    }
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  // The ONLY code that touches `history` and `pathname` together, so the
  // two can never diverge. Pushing (not replacing) a history entry is the
  // whole mechanism behind a working Back button.
  function _navigate(next: string) {
    if (typeof window !== "undefined" && window.location.pathname !== next) {
      window.history.pushState({}, "", next);
    }
    setPathname(next);
  }

  // The single tab-navigation entry point (handleMapped, handleTabChange,
  // handleSignedIn all route through this). Leaving a tab also dismisses an
  // open auth overlay -- today's behaviour, preserved.
  function navigateTo(tab: string) {
    setAuthView(null);
    _navigate(pathForTab(tab, TAB_VALUES));
  }

  // Deliberately does NOT touch authView: VerifyLanding's CTA calls
  // goToApp() and THEN setAuthView("signin"), so goToApp must not clear the
  // overlay the caller is about to open. Not folded into navigateTo(TABS[0]
  // .value) for the same reason -- that would make the CTA depend on
  // setState ordering to survive.
  function goToApp() {
    _navigate("/");
  }

  function handleMapped(response: MappingResponse, fieldSet: FieldSetPayload) {
    setLastMapping(response);
    setLastFieldSet(fieldSet);
    navigateTo("review");
  }

  function handleTabChange(value: string) {
    navigateTo(value);
  }

  function handleSignedIn(user: AuthUser) {
    const returnTo = pendingReturnTo(authState);
    dispatch({ type: "SIGN_IN_SUCCESS", user });
    toast.success(`Signed in as ${user.email}.`);
    setAuthView(null);
    if (returnTo === "review") {
      navigateTo("review");
    }
  }

  async function handleSignOut() {
    try {
      await signOut();
    } finally {
      // The server clears the cookie; reflect it client-side regardless so a
      // transient network hiccup never leaves a stale "signed in" chip.
      dispatch({ type: "SIGN_OUT" });
      toast.success("Signed out.");
    }
  }

  function handleOpenSignIn() {
    setAuthView("signin");
  }

  // The SignInRequiredGate's secondary CTA (D-10-13) -- reuses the SAME
  // authView overlay state machine already wired for Sign In, never a
  // second one.
  function handleOpenSignUp() {
    setAuthView("signup");
  }

  function handleRequireSignIn() {
    // From the ConfirmGate: stamp the return destination, then open Sign In.
    dispatch({ type: "SET_RETURN_TO", returnTo: "review" });
    setAuthView("signin");
  }

  // Verification landing is a standalone route reached only via the console
  // link -- it renders without the tab shell. Checked BEFORE the tab shell
  // renders, so /verify is never routed through the tab allowlist even
  // though tabs and /verify now share one pathname axis (D-2).
  if (pathname.startsWith("/verify")) {
    return (
      <>
        <VerifyLanding
          onSignIn={() => {
            goToApp();
            setAuthView("signin");
          }}
        />
        <Toaster />
      </>
    );
  }

  const signedIn = isSignedIn(authState);
  const verified = isVerified(authState);
  const redirectedFromConfirm = pendingReturnTo(authState) === "review";

  return (
    <>
      <AppShell
        tabs={TABS}
        activeTab={activeTab}
        onTabChange={handleTabChange}
        trailing={
          <SignedInIndicator state={authState} onSignIn={handleOpenSignIn} onSignOut={handleSignOut} />
        }
      >
        {authView === "signin" ? (
          <SignInScreen
            googleEnabled={googleEnabled}
            redirectedFromConfirm={redirectedFromConfirm}
            onSignedIn={handleSignedIn}
            onSwitchToSignUp={() => setAuthView("signup")}
          />
        ) : authView === "signup" ? (
          <SignUpScreen googleEnabled={googleEnabled} onSwitchToSignIn={() => setAuthView("signin")} />
        ) : (
          <>
            {/* Schemas/Upload/Review are gated app-wide (D-10-13, INGEST-06):
                a signed-out visitor sees the SAME interstitial on all three,
                never the real content. Docs stays open -- a prospective
                user reading what the tool does before creating an account
                is a deliberate exception (10-UI-SPEC Discretion §3). Tabs
                remain visible/clickable while signed out for orientation. */}
            {activeTab === "schemas" &&
              (signedIn ? (
                <Schemas verified={verified} />
              ) : (
                <SignInRequiredGate onSignIn={handleOpenSignIn} onCreateAccount={handleOpenSignUp} />
              ))}
            {activeTab === "upload" &&
              (signedIn ? (
                <Upload
                  onMapped={handleMapped}
                  signedIn={signedIn}
                  verified={verified}
                  onRequireSignIn={handleRequireSignIn}
                />
              ) : (
                <SignInRequiredGate onSignIn={handleOpenSignIn} onCreateAccount={handleOpenSignUp} />
              ))}
            {activeTab === "review" &&
              (signedIn ? (
                // Keyed by upload_token so a fresh upload (including a
                // same-signature re-upload for the UI-06 money shot) always
                // remounts Review with fresh local resolution state, rather
                // than this screen trying to detect "a new mapping arrived"
                // via an effect.
                <Review
                  key={lastMapping?.upload_token ?? "empty"}
                  mapping={lastMapping}
                  fieldSet={lastFieldSet}
                  signedIn={signedIn}
                  verified={verified}
                  onRequireSignIn={handleRequireSignIn}
                />
              ) : (
                <SignInRequiredGate onSignIn={handleOpenSignIn} onCreateAccount={handleOpenSignUp} />
              ))}
            {activeTab === "docs" && <Documentation />}
          </>
        )}
      </AppShell>
      <Toaster />
    </>
  );
}

export default App;

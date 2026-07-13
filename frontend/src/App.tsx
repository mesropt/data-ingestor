import { useEffect, useReducer, useState } from "react";
import { toast } from "sonner";

import { AppShell, type AppTab } from "@/components/AppShell";
import { ReviewGroupTabs } from "@/components/ReviewGroupTabs";
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
import type { AuthUser, MappingResponse, SheetGroupResponse } from "@/lib/types";
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
  // The label is the full word (quick 260712) -- "Docs" read as developer
  // shorthand; the tab holds the product's user documentation. The VALUE
  // stays "docs": it is the /docs route path, and renaming a path would
  // ripple into api/routes/docs_paths for zero user benefit.
  { value: "docs", label: "Documentation" },
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
  // D-10-02/06: the governed Schema name Upload's `SchemaPicker` resolved --
  // replaces the serialized target-fields payload this state used to carry
  // (Review no longer accepts/renders a second Schema selector, Discretion §6).
  const [lastSchemaName, setLastSchemaName] = useState<string | null>(null);
  // 11-10 (D-11-10): the latest sheet group and its per-sheet Schema choices
  // + headers-only flag, mutually exclusive with `lastMapping` -- the Review
  // tab shows whichever ingest arrived LAST, so the two are cleared
  // crosswise in handleMapped/handleSheetGroup, never left to disagree.
  const [lastGroup, setLastGroup] = useState<SheetGroupResponse | null>(null);
  const [lastGroupSchemas, setLastGroupSchemas] = useState<Record<string, string>>({});
  const [lastGroupHeadersOnly, setLastGroupHeadersOnly] = useState(false);
  // The vendor the curator named on Upload. Review no longer asks a second
  // time: a file whose headers matched the seeded starter aliases used to reach
  // Confirm pre-filled with vendor "starter" -- a seed label, not a lab. Asked
  // once, where the curator actually knows the answer, and threaded from there.
  const [lastVendor, setLastVendor] = useState("");
  // A one-way tick that asks the (still-mounted) Upload screen to re-open the
  // sheet question it already answered. A counter, not a boolean: pressing Back
  // twice must fire twice, and a boolean that is already `true` fires once.
  const [backSignal, setBackSignal] = useState(0);

  /** Back, from the Review tabs to the table/sheet selection they came from.
   * Nothing is thrown away: the workbook is still retained under the same upload
   * token server-side, Upload never unmounted, and every resolution already made
   * in a Review tab survives in that tab. */
  function handleBackToSheets() {
    setBackSignal((tick) => tick + 1);
    navigateTo("upload");
  }

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

  function handleMapped(response: MappingResponse, schemaName: string, vendor: string) {
    setLastMapping(response);
    setLastSchemaName(schemaName);
    setLastVendor(vendor);
    // A fresh single-dataset ingest supersedes any earlier group on the
    // Review tab (and vice versa in handleSheetGroup).
    setLastGroup(null);
    navigateTo("review");
  }

  function handleSheetGroup(
    group: SheetGroupResponse,
    schemasBySheet: Record<string, string>,
    headersOnly: boolean,
    vendor: string
  ) {
    setLastGroup(group);
    setLastGroupSchemas(schemasBySheet);
    setLastGroupHeadersOnly(headersOnly);
    setLastVendor(vendor);
    setLastMapping(null);
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
                never the real content. Documentation stays open -- a prospective
                user reading what the tool does before creating an account
                is a deliberate exception (10-UI-SPEC Discretion §3). Tabs
                remain visible/clickable while signed out for orientation. */}
            {activeTab === "schemas" &&
              (signedIn ? (
                <Schemas verified={verified} />
              ) : (
                <SignInRequiredGate onSignIn={handleOpenSignIn} onCreateAccount={handleOpenSignUp} />
              ))}
            {/* Upload and Review are HIDDEN when inactive, never unmounted.
                Both hold work the curator did by hand -- a half-answered sheet
                question, a column of amber fields they resolved one by one --
                and React destroys a component's state the moment it leaves the
                tree. Switching to Schemas to add a missing field and coming back
                silently threw all of it away. The tab strip is navigation, not a
                reason to discard someone's answers. */}
            {(activeTab === "upload" || activeTab === "review") && !signedIn && (
              <SignInRequiredGate onSignIn={handleOpenSignIn} onCreateAccount={handleOpenSignUp} />
            )}
            {signedIn && (
              <div className={activeTab === "upload" ? undefined : "hidden"}>
                <Upload
                  onMapped={handleMapped}
                  onSheetGroup={handleSheetGroup}
                  backSignal={backSignal}
                  signedIn={signedIn}
                  verified={verified}
                  onRequireSignIn={handleRequireSignIn}
                />
              </div>
            )}
            {signedIn && (
              <div className={activeTab === "review" ? undefined : "hidden"}>
                {lastGroup ? (
                  // 11-10 (D-11-10): a resolved sheet group lands here as N
                  // member tabs, each holding the whole existing Review on
                  // its own gate. Keyed by group_id so a NEW workbook's
                  // group remounts with fresh member state, exactly the
                  // single path's upload_token keying below -- while a tab
                  // switch inside one group changes no key at all.
                  <ReviewGroupTabs
                    key={lastGroup.group_id}
                    group={lastGroup}
                    schemasBySheet={lastGroupSchemas}
                    onBack={handleBackToSheets}
                    headersOnly={lastGroupHeadersOnly}
                    vendor={lastVendor}
                    signedIn={signedIn}
                    verified={verified}
                    onRequireSignIn={handleRequireSignIn}
                  />
                ) : (
                  // Keyed by upload_token so a fresh upload (including a
                  // same-signature re-upload for the UI-06 money shot) always
                  // remounts Review with fresh local resolution state, rather
                  // than this screen trying to detect "a new mapping arrived"
                  // via an effect.
                  <Review
                    key={lastMapping?.upload_token ?? "empty"}
                    mapping={lastMapping}
                    schemaName={lastSchemaName}
                    vendor={lastVendor}
                    signedIn={signedIn}
                    verified={verified}
                    onRequireSignIn={handleRequireSignIn}
                  />
                )}
              </div>
            )}
            {activeTab === "docs" && <Documentation />}
          </>
        )}
      </AppShell>
      <Toaster />
    </>
  );
}

export default App;

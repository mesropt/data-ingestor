import { useEffect, useReducer, useState } from "react";
import { toast } from "sonner";

import { AppShell, type AppTab } from "@/components/AppShell";
import { SignedInIndicator } from "@/components/SignedInIndicator";
import { SignInScreen } from "@/components/SignInScreen";
import { SignUpScreen } from "@/components/SignUpScreen";
import { VerifyLanding } from "@/components/VerifyLanding";
import { Toaster } from "@/components/ui/sonner";
import { DefineFields } from "@/screens/DefineFields";
import { Registry } from "@/screens/Registry";
import { Review } from "@/screens/Review";
import { Upload } from "@/screens/Upload";
import { getAuthConfig, getMe, signOut } from "@/lib/api";
import type { AuthUser, FieldSetPayload, MappingResponse } from "@/lib/types";
import { authReducer, initialAuthState, isSignedIn, isVerified } from "@/state/auth";

const TABS: AppTab[] = [
  { value: "define-fields", label: "Define Fields" },
  { value: "upload", label: "Upload" },
  { value: "review", label: "Review" },
  { value: "registry", label: "Registry" },
];

type AuthView = "signin" | "signup" | null;

/** The pending post-sign-in destination the store carried while signed out
 * (stamped by SET_RETURN_TO from the ConfirmGate "Sign In to Confirm" flow). */
function pendingReturnTo(state: ReturnType<typeof authReducer>): string | undefined {
  return "returnTo" in state ? state.returnTo : undefined;
}

function App() {
  const [activeTab, setActiveTab] = useState<string>(TABS[0].value);
  const [lastMapping, setLastMapping] = useState<MappingResponse | null>(null);
  const [lastFieldSet, setLastFieldSet] = useState<FieldSetPayload | null>(null);

  const [authState, dispatch] = useReducer(authReducer, initialAuthState);
  const [googleEnabled, setGoogleEnabled] = useState(false);
  const [authView, setAuthView] = useState<AuthView>(null);
  // The console-printed verification link lands on /verify?token=... -- a
  // tiny router-free switch, tracked in state so the landing's CTA can
  // navigate back into the shell without a full reload.
  const [path, setPath] = useState<string>(() =>
    typeof window === "undefined" ? "/" : window.location.pathname
  );

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

  function goToApp() {
    if (typeof window !== "undefined" && window.location.pathname !== "/") {
      window.history.pushState({}, "", "/");
    }
    setPath("/");
  }

  function handleMapped(response: MappingResponse, fieldSet: FieldSetPayload) {
    setLastMapping(response);
    setLastFieldSet(fieldSet);
    setAuthView(null);
    setActiveTab("review");
  }

  function handleTabChange(value: string) {
    // Leaving via a tab click also dismisses any open auth overlay.
    setAuthView(null);
    setActiveTab(value);
  }

  function handleSignedIn(user: AuthUser) {
    const returnTo = pendingReturnTo(authState);
    dispatch({ type: "SIGN_IN_SUCCESS", user });
    toast.success(`Signed in as ${user.email}.`);
    setAuthView(null);
    if (returnTo === "review") {
      setActiveTab("review");
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

  function handleRequireSignIn() {
    // From the ConfirmGate: stamp the return destination, then open Sign In.
    dispatch({ type: "SET_RETURN_TO", returnTo: "review" });
    setAuthView("signin");
  }

  // Verification landing is a standalone route reached only via the console
  // link -- it renders without the tab shell.
  if (path.startsWith("/verify")) {
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
            {activeTab === "define-fields" && <DefineFields />}
            {activeTab === "upload" && (
              <Upload
                onMapped={handleMapped}
                signedIn={signedIn}
                verified={verified}
                onRequireSignIn={handleRequireSignIn}
              />
            )}
            {activeTab === "review" && (
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
            )}
            {activeTab === "registry" && <Registry />}
          </>
        )}
      </AppShell>
      <Toaster />
    </>
  );
}

export default App;

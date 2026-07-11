import { afterEach, describe, expect, it, vi } from "vitest";

import {
  authReducer,
  initialAuthState,
  isGovernedActionAllowed,
  isSignedIn,
  isVerified,
  type AuthState,
} from "./auth";
import {
  ApiError,
  getAuthConfig,
  getMe,
  signIn,
  signOut,
  signUp,
  verifyEmail,
} from "../lib/api";
import type { AuthUser } from "../lib/types";

const verifiedUser: AuthUser = {
  id: "u-1",
  email: "curator@example.com",
  is_verified: true,
  auth_provider: "password",
};

const unverifiedUser: AuthUser = {
  id: "u-2",
  email: "new@example.com",
  is_verified: false,
  auth_provider: "password",
};

describe("authReducer", () => {
  it("starts in the probing phase", () => {
    expect(initialAuthState).toEqual({ phase: "probing" });
  });

  it("SESSION_RESOLVED with a user moves probing -> signedIn carrying email + is_verified", () => {
    const state = authReducer(initialAuthState, { type: "SESSION_RESOLVED", user: unverifiedUser });

    expect(state).toEqual({ phase: "signedIn", user: unverifiedUser });
    // Immutable: the original state object is untouched.
    expect(initialAuthState).toEqual({ phase: "probing" });
  });

  it("SESSION_RESOLVED with a null user moves probing -> signedOut", () => {
    const state = authReducer(initialAuthState, { type: "SESSION_RESOLVED", user: null });

    expect(state).toEqual({ phase: "signedOut" });
  });

  it("SIGN_IN_SUCCESS moves signedOut -> signedIn", () => {
    const signedOut: AuthState = { phase: "signedOut" };

    const state = authReducer(signedOut, { type: "SIGN_IN_SUCCESS", user: verifiedUser });

    expect(state).toEqual({ phase: "signedIn", user: verifiedUser });
    expect(signedOut).toEqual({ phase: "signedOut" });
  });

  it("SIGN_OUT moves signedIn -> signedOut, dropping the user", () => {
    const signedIn: AuthState = { phase: "signedIn", user: verifiedUser };

    const state = authReducer(signedIn, { type: "SIGN_OUT" });

    expect(state).toEqual({ phase: "signedOut" });
  });

  it("carries a returnTo through SIGN_IN_SUCCESS so a redirected-from-Confirm sign-in can route back", () => {
    // The user clicked "Sign In to Confirm" on Review: SET_RETURN_TO stamps
    // the destination, then the sign-in completes -- the destination must
    // survive so App can navigate back to Review.
    const withReturn = authReducer({ phase: "signedOut" }, { type: "SET_RETURN_TO", returnTo: "review" });
    expect(withReturn).toEqual({ phase: "signedOut", returnTo: "review" });

    const signedIn = authReducer(withReturn, { type: "SIGN_IN_SUCCESS", user: verifiedUser });
    expect(signedIn).toEqual({ phase: "signedIn", user: verifiedUser, returnTo: "review" });
  });

  it("is a no-op for an action that doesn't apply to the current phase", () => {
    // SIGN_OUT while already signed out changes nothing.
    const signedOut: AuthState = { phase: "signedOut", returnTo: "review" };
    expect(authReducer(signedOut, { type: "SIGN_OUT" })).toEqual({ phase: "signedOut" });
  });

  it("SET_RETURN_TO is a no-op while probing -- too early to know signed-in status, so it must not force signedOut", () => {
    const state = authReducer({ phase: "probing" }, { type: "SET_RETURN_TO", returnTo: "review" });
    expect(state).toEqual({ phase: "probing" });
  });

  it("SESSION_RESOLVED with a user carries forward a pending returnTo, mirroring SIGN_IN_SUCCESS", () => {
    const priorState: AuthState = { phase: "signedOut", returnTo: "review" };

    const state = authReducer(priorState, { type: "SESSION_RESOLVED", user: verifiedUser });

    expect(state).toEqual({ phase: "signedIn", user: verifiedUser, returnTo: "review" });
  });
});

describe("auth selectors", () => {
  it("isSignedIn is true only in the signedIn phase", () => {
    expect(isSignedIn({ phase: "signedIn", user: verifiedUser })).toBe(true);
    expect(isSignedIn({ phase: "signedOut" })).toBe(false);
    expect(isSignedIn({ phase: "probing" })).toBe(false);
  });

  it("isVerified is true only when signedIn AND the user is verified", () => {
    expect(isVerified({ phase: "signedIn", user: verifiedUser })).toBe(true);
    expect(isVerified({ phase: "signedIn", user: unverifiedUser })).toBe(false);
    expect(isVerified({ phase: "signedOut" })).toBe(false);
  });

  it("isGovernedActionAllowed mirrors server require_verified_user: signedIn AND verified", () => {
    expect(isGovernedActionAllowed({ phase: "signedIn", user: verifiedUser })).toBe(true);
    expect(isGovernedActionAllowed({ phase: "signedIn", user: unverifiedUser })).toBe(false);
    expect(isGovernedActionAllowed({ phase: "signedOut" })).toBe(false);
    expect(isGovernedActionAllowed({ phase: "probing" })).toBe(false);
  });
});

describe("auth api client", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  function mockOnce(body: unknown, status = 200): ReturnType<typeof vi.fn> {
    const fetchMock = vi.fn().mockImplementation(
      async () =>
        new Response(body === undefined ? null : JSON.stringify(body), {
          status,
          headers: { "Content-Type": "application/json" },
        })
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;
    return fetchMock;
  }

  it("signUp POSTs /api/auth/signup with credentials:'include' and returns the accepted message", async () => {
    const fetchMock = mockOnce({ message: "Check your server console." });

    const result = await signUp({ email: "new@example.com", password: "password123" });

    const [path, options] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/auth/signup");
    expect(options.method).toBe("POST");
    expect(options.credentials).toBe("include");
    expect(JSON.parse(options.body as string)).toEqual({ email: "new@example.com", password: "password123" });
    expect(result).toEqual({ message: "Check your server console." });
  });

  it("signIn POSTs /api/auth/login and returns the AuthUser", async () => {
    const fetchMock = mockOnce(verifiedUser);

    const result = await signIn({ email: "curator@example.com", password: "password123" });

    const [path, options] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/auth/login");
    expect(options.method).toBe("POST");
    expect(options.credentials).toBe("include");
    expect(result).toEqual(verifiedUser);
  });

  it("signOut POSTs /api/auth/logout with credentials:'include'", async () => {
    const fetchMock = mockOnce({ status: "signed out" });

    await signOut();

    const [path, options] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/auth/logout");
    expect(options.method).toBe("POST");
    expect(options.credentials).toBe("include");
  });

  it("getMe GETs /api/auth/me and returns the AuthUser", async () => {
    const fetchMock = mockOnce(verifiedUser);

    const result = await getMe();

    const [path, options] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/auth/me");
    expect(options.method).toBe("GET");
    expect(options.credentials).toBe("include");
    expect(result).toEqual(verifiedUser);
  });

  it("getMe raises a typed ApiError on a 401 (the caller treats it as signed-out)", async () => {
    mockOnce({ detail: "Not signed in." }, 401);

    await expect(getMe()).rejects.toBeInstanceOf(ApiError);
  });

  it("verifyEmail GETs /api/auth/verify with the token in the query string", async () => {
    const fetchMock = mockOnce({ status: "verified" });

    const result = await verifyEmail("tok-123");

    const [path, options] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/auth/verify?token=tok-123");
    expect(options.method).toBe("GET");
    expect(options.credentials).toBe("include");
    expect(result).toEqual({ status: "verified" });
  });

  it("getAuthConfig GETs /api/auth/config and returns the google flag", async () => {
    const fetchMock = mockOnce({ google_oauth_enabled: false });

    const result = await getAuthConfig();

    const [path, options] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/auth/config");
    expect(options.method).toBe("GET");
    expect(options.credentials).toBe("include");
    expect(result).toEqual({ google_oauth_enabled: false });
  });
});

import { defineStore } from "pinia";

import { request } from "../api/http";

/**
 * Hold authentication state and first-run bootstrap state for the admin UI.
 */
export const useAuthStore = defineStore("auth", {
  state: () => ({
    accessToken: window.localStorage.getItem("access_token"),
    refreshToken: window.localStorage.getItem("refresh_token"),
    bootstrapStatus: null,
    challenge: null
  }),
  getters: {
    /**
     * Check whether the user currently has an access token.
     *
     * Returns:
     *   True when an access token exists in local state.
     */
    isAuthenticated(state) {
      return Boolean(state.accessToken);
    }
  },
  actions: {
    /**
     * Persist the active session tokens to local storage.
     *
     * Args:
     *   accessToken: New access token.
     *   refreshToken: New refresh token.
     *
     * Returns:
     *   None. Store state and local storage are updated.
     */
    setSession(accessToken, refreshToken) {
      this.accessToken = accessToken;
      this.refreshToken = refreshToken;
      window.localStorage.setItem("access_token", accessToken);
      window.localStorage.setItem("refresh_token", refreshToken);
    },

    /**
     * Clear all local authentication state.
     *
     * Returns:
     *   None. Store state and local storage are reset.
     */
    logout() {
      this.accessToken = null;
      this.refreshToken = null;
      this.challenge = null;
      window.localStorage.removeItem("access_token");
      window.localStorage.removeItem("refresh_token");
    },

    /**
     * Fetch the backend bootstrap state.
     *
     * Returns:
     *   Loaded bootstrap status payload.
     */
    async loadBootstrapStatus() {
      this.bootstrapStatus = await request("/api/auth/bootstrap-status");
      return this.bootstrapStatus;
    },

    /**
     * Start the password stage of login.
     *
     * Args:
     *   username: Administrator username.
     *   password: Administrator password.
     *
     * Returns:
     *   Challenge payload returned by the backend.
     */
    async login(username, password) {
      this.challenge = await request("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password })
      });
      return this.challenge;
    },

    /**
     * Complete the TOTP second-factor flow.
     *
     * Args:
     *   code: User supplied TOTP code.
     *
     * Returns:
     *   Final token pair.
     */
    async verifyTotp(code) {
      const result = await request("/api/auth/2fa/totp/verify", {
        method: "POST",
        body: JSON.stringify({
          challenge_token: this.challenge?.challenge_token,
          code
        })
      });
      this.setSession(result.access_token, result.refresh_token);
      return result;
    }
  }
});


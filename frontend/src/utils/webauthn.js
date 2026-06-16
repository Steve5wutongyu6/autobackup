/**
 * Convert a base64url string into a Uint8Array for WebAuthn APIs.
 *
 * Args:
 *   value: Base64url-encoded string from the backend.
 *
 * Returns:
 *   Binary Uint8Array representation for browser credential methods.
 */
export function base64UrlToUint8Array(value) {
  const paddedValue = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  const binary = window.atob(paddedValue);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

/**
 * Convert raw WebAuthn binary data into a base64url string for transport.
 *
 * Args:
 *   value: ArrayBuffer or Uint8Array from the browser credential object.
 *
 * Returns:
 *   Base64url string safe for JSON transport.
 */
export function uint8ArrayToBase64Url(value) {
  const bytes = value instanceof Uint8Array ? value : new Uint8Array(value);
  const binary = Array.from(bytes, (byte) => String.fromCharCode(byte)).join("");
  return window.btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

/**
 * Convert registration options received from the backend into browser-ready form.
 *
 * Args:
 *   publicKey: JSON-safe WebAuthn creation options from the backend.
 *
 * Returns:
 *   Browser-ready publicKey object with binary challenge and user ID fields.
 */
export function normalizeRegistrationOptions(publicKey) {
  return {
    ...publicKey,
    challenge: base64UrlToUint8Array(publicKey.challenge),
    user: {
      ...publicKey.user,
      id: base64UrlToUint8Array(publicKey.user.id)
    },
    excludeCredentials: (publicKey.excludeCredentials || []).map((credential) => ({
      ...credential,
      id: base64UrlToUint8Array(credential.id)
    }))
  };
}

/**
 * Convert authentication options received from the backend into browser-ready form.
 *
 * Args:
 *   publicKey: JSON-safe WebAuthn request options from the backend.
 *
 * Returns:
 *   Browser-ready publicKey object with binary challenge and credential IDs.
 */
export function normalizeAuthenticationOptions(publicKey) {
  return {
    ...publicKey,
    challenge: base64UrlToUint8Array(publicKey.challenge),
    allowCredentials: (publicKey.allowCredentials || []).map((credential) => ({
      ...credential,
      id: base64UrlToUint8Array(credential.id)
    }))
  };
}

/**
 * Serialize a browser registration response into JSON-safe WebAuthn payload data.
 *
 * Args:
 *   credential: PublicKeyCredential returned by navigator.credentials.create.
 *
 * Returns:
 *   JSON-safe object for the backend registration verification API.
 */
export function serializeRegistrationCredential(credential) {
  return {
    id: credential.id,
    rawId: uint8ArrayToBase64Url(credential.rawId),
    type: credential.type,
    response: {
      attestationObject: uint8ArrayToBase64Url(credential.response.attestationObject),
      clientDataJSON: uint8ArrayToBase64Url(credential.response.clientDataJSON),
      transports: credential.response.getTransports ? credential.response.getTransports() : []
    },
    clientExtensionResults: credential.getClientExtensionResults()
  };
}

/**
 * Serialize a browser authentication response into JSON-safe WebAuthn payload data.
 *
 * Args:
 *   credential: PublicKeyCredential returned by navigator.credentials.get.
 *
 * Returns:
 *   JSON-safe object for the backend authentication verification API.
 */
export function serializeAuthenticationCredential(credential) {
  return {
    id: credential.id,
    rawId: uint8ArrayToBase64Url(credential.rawId),
    type: credential.type,
    response: {
      authenticatorData: uint8ArrayToBase64Url(credential.response.authenticatorData),
      clientDataJSON: uint8ArrayToBase64Url(credential.response.clientDataJSON),
      signature: uint8ArrayToBase64Url(credential.response.signature),
      userHandle: credential.response.userHandle
        ? uint8ArrayToBase64Url(credential.response.userHandle)
        : null
    },
    clientExtensionResults: credential.getClientExtensionResults()
  };
}

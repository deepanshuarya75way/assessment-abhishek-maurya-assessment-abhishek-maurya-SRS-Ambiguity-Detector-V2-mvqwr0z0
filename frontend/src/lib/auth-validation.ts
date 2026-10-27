/**
 * Client-side auth validation — immediate UX feedback ONLY. The backend remains
 * authoritative (the project contract: never trust the client). Rules mirror
 * `app/schemas/auth.py` + the service policy; each returns an error message or null.
 */

/** Mirrors backend PASSWORD_MIN/MAX_LENGTH (UX copy only — server enforces). */
export const PASSWORD_MIN_LENGTH = 12;
export const PASSWORD_MAX_LENGTH = 256;
/** Mirrors backend VerifyEmail/ResetPassword token length bounds. */
export const TOKEN_MIN_LENGTH = 16;
export const TOKEN_MAX_LENGTH = 128;
export const NAME_MAX_LENGTH = 100;
export const EMAIL_MAX_LENGTH = 320;

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Collapse inner whitespace (mirrors the server's name validator). */
export function collapseName(value: string): string {
  return value.split(/\s+/).join(" ").trim();
}

/** Trim + lowercase (mirrors server email normalization for UX consistency). */
export function normalizeEmail(value: string): string {
  return value.trim().toLowerCase();
}

export function validateEmail(value: string): string | null {
  const email = value.trim();
  if (!email) return "Enter your email address.";
  if (email.length > EMAIL_MAX_LENGTH) return "That email address is too long.";
  if (!EMAIL_PATTERN.test(email)) return "Enter a valid email address.";
  return null;
}

export function validateName(value: string): string | null {
  const name = collapseName(value);
  if (!name) return "Enter your name.";
  if (name.length > NAME_MAX_LENGTH) return "Use at most 100 characters for your name.";
  return null;
}

/**
 * Password policy mirror: length + email-local-part rule. The server ALSO applies
 * a common-password denylist the client deliberately does not duplicate (drift risk);
 * denylist rejections surface as `password_too_weak` with guidance to try again.
 */
export function validatePassword(password: string, email?: string): string | null {
  if (!password) return "Enter a password.";
  if (password.length < PASSWORD_MIN_LENGTH) {
    return `Use at least ${PASSWORD_MIN_LENGTH} characters.`;
  }
  if (password.length > PASSWORD_MAX_LENGTH) {
    return `Use at most ${PASSWORD_MAX_LENGTH} characters.`;
  }
  if (email) {
    const local = normalizeEmail(email).split("@")[0] ?? "";
    if (local.length >= 4 && password.toLowerCase().includes(local)) {
      return "Don't include your email address in your password.";
    }
  }
  return null;
}

export function validateConfirmPassword(password: string, confirm: string): string | null {
  if (!confirm) return "Confirm your password.";
  if (password !== confirm) return "Passwords don't match.";
  return null;
}

export function validateCurrentPassword(value: string): string | null {
  if (!value) return "Enter your current password.";
  if (value.length > PASSWORD_MAX_LENGTH) {
    return `Use at most ${PASSWORD_MAX_LENGTH} characters.`;
  }
  return null;
}

/** Link tokens: structural check only (never log or display the value itself). */
export function validateToken(value: string | null): string | null {
  if (!value || value.length < TOKEN_MIN_LENGTH || value.length > TOKEN_MAX_LENGTH) {
    return "invalid";
  }
  return null;
}

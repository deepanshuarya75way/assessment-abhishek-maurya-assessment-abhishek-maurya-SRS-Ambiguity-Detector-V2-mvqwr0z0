import { describe, expect, it } from "vitest";

import {
  collapseName,
  normalizeEmail,
  validateConfirmPassword,
  validateCurrentPassword,
  validateEmail,
  validateName,
  validatePassword,
  validateToken,
} from "./auth-validation";

describe("auth validation", () => {
  describe("validateEmail", () => {
    it("accepts a normal address", () => {
      expect(validateEmail("ada@example.com")).toBeNull();
    });

    it("requires a value", () => {
      expect(validateEmail("")).toBe("Enter your email address.");
      expect(validateEmail("   ")).toBe("Enter your email address.");
    });

    it("rejects malformed addresses", () => {
      expect(validateEmail("not-an-email")).toBe("Enter a valid email address.");
      expect(validateEmail("a@b")).toBe("Enter a valid email address.");
      expect(validateEmail("a b@c.de")).toBe("Enter a valid email address.");
    });

    it("rejects overlong addresses", () => {
      expect(validateEmail(`${"a".repeat(313)}@b.co.uk`)).toBe("That email address is too long.");
      expect(validateEmail(`${"a".repeat(312)}@b.co.uk`)).toBeNull();
    });
  });

  describe("validateName", () => {
    it("accepts a normal name", () => {
      expect(validateName("Ada Lovelace")).toBeNull();
    });

    it("rejects blank names", () => {
      expect(validateName("")).toBe("Enter your name.");
      expect(validateName("   ")).toBe("Enter your name.");
    });

    it("rejects names over 100 characters", () => {
      expect(validateName("a".repeat(101))).toBe("Use at most 100 characters for your name.");
      expect(validateName("a".repeat(100))).toBeNull();
    });
  });

  describe("validatePassword", () => {
    it("accepts a strong password", () => {
      expect(validatePassword("correct-horse-battery9", "ada@example.com")).toBeNull();
    });

    it("requires a value", () => {
      expect(validatePassword("")).toBe("Enter a password.");
    });

    it("enforces the 12–256 window", () => {
      expect(validatePassword("short-11!")).toBe("Use at least 12 characters.");
      expect(validatePassword("a".repeat(11))).toBe("Use at least 12 characters.");
      expect(validatePassword("a".repeat(12))).toBeNull();
      expect(validatePassword("a".repeat(257))).toBe("Use at most 256 characters.");
    });

    it("rejects passwords containing the email local part (case-insensitive)", () => {
      expect(validatePassword("xxJOHN.DOEyy12", "John.Doe@example.com")).toBe(
        "Don't include your email address in your password.",
      );
    });

    it("ignores local parts shorter than 4 characters", () => {
      expect(validatePassword("ab-contains-ab-12", "ab@example.com")).toBeNull();
    });

    it("skips the local-part rule without an email", () => {
      expect(validatePassword("no-email-context12")).toBeNull();
    });
  });

  describe("validateConfirmPassword", () => {
    it("accepts matching passwords", () => {
      expect(validateConfirmPassword("same-password-1", "same-password-1")).toBeNull();
    });

    it("requires a value", () => {
      expect(validateConfirmPassword("password-12x", "")).toBe("Confirm your password.");
    });

    it("rejects mismatches", () => {
      expect(validateConfirmPassword("password-12x", "password-12y")).toBe(
        "Passwords don't match.",
      );
    });
  });

  describe("validateCurrentPassword", () => {
    it("accepts any non-empty value", () => {
      expect(validateCurrentPassword("whatever-it-is")).toBeNull();
    });

    it("requires a value", () => {
      expect(validateCurrentPassword("")).toBe("Enter your current password.");
    });
  });

  describe("validateToken", () => {
    it("accepts link tokens in the 16–128 window", () => {
      expect(validateToken("t".repeat(16))).toBeNull();
      expect(validateToken("t".repeat(43))).toBeNull();
      expect(validateToken("t".repeat(128))).toBeNull();
    });

    it("rejects missing or out-of-window tokens", () => {
      expect(validateToken(null)).toBe("invalid");
      expect(validateToken("")).toBe("invalid");
      expect(validateToken("t".repeat(15))).toBe("invalid");
      expect(validateToken("t".repeat(129))).toBe("invalid");
    });
  });

  describe("normalizers", () => {
    it("collapses inner name whitespace", () => {
      expect(collapseName("  Ada   Lovelace  ")).toBe("Ada Lovelace");
    });

    it("trims and lowercases emails", () => {
      expect(normalizeEmail("  ADA@Ex.COM ")).toBe("ada@ex.com");
    });
  });
});

import { describe, expect, it } from "vitest";
import { parseConnectionQr } from "./android-connection-qr";

const code = "orion_enroll_" + "a".repeat(43);
const origin = "https://host.example.ts.net";
const payload = { type: "orion-connect", version: 1, origin, code };

describe("Android connection QR", () => {
  it("reads the HTTPS origin and one-time enrollment code", () => {
    expect(parseConnectionQr(JSON.stringify(payload))).toEqual({ origin, code });
  });

  it.each([
    "http://host.example.ts.net",
    "https://host.example.ts.net.evil.test",
    "https://owner@host.example.ts.net",
    "https://host.example.ts.net/api/auth/native/enroll",
    "https://host.example.ts.net?token=untrusted",
  ])("rejects an invalid origin %s", (invalid) => {
    expect(() => parseConnectionQr(JSON.stringify({ ...payload, origin: invalid }))).toThrow();
  });

  it("rejects Authenticator QR, access tokens and unsupported versions", () => {
    expect(() => parseConnectionQr("otpauth://totp/Orion:Owner")).toThrow();
    expect(() =>
      parseConnectionQr(JSON.stringify({ ...payload, code: "orion_access_fixture" })),
    ).toThrow();
    expect(() => parseConnectionQr(JSON.stringify({ ...payload, version: 2 }))).toThrow();
  });
});

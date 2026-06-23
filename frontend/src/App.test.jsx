// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import App from "./App";

// App fires fetch() on mount and auto-scrolls the chat; stub both so the
// component renders cleanly under jsdom (which implements neither).
beforeEach(() => {
  window.HTMLElement.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.reject(new Error("offline")))
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("renders the CONTROLPC brand and the chat composer", () => {
    render(<App />);
    expect(screen.getByText("CONTROLPC")).toBeTruthy();
    expect(
      screen.getByPlaceholderText(/Type a message or a control command/i)
    ).toBeTruthy();
  });

  it("starts in the idle/Ready state", () => {
    render(<App />);
    expect(screen.getByText("Ready")).toBeTruthy();
  });
});

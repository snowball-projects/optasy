import test from "node:test";
import assert from "node:assert/strict";
import { attachPopover, isPopoverOpen } from "../web/popover.mjs";

// These passive events must not require a document or create a panel. Actual
// button activation and dismissal are checked in the rendered browser.
test("hover, focus and touch contact alone never open player details", () => {
  const trigger = new EventTarget();
  const attributes = new Map();
  trigger.setAttribute = (key, value) => attributes.set(key, value);
  trigger.getAttribute = (key) => attributes.get(key);
  trigger.removeAttribute = (key) => attributes.delete(key);
  trigger.isConnected = true;
  const cleanup = attachPopover(trigger, () => {
    assert.fail("Passive interaction must not request player details");
  });
  for (const type of [
    "pointerenter",
    "mouseenter",
    "mouseover",
    "focus",
    "focusin",
    "touchstart",
    "pointerdown",
  ]) {
    trigger.dispatchEvent(new Event(type));
    assert.equal(isPopoverOpen(), false);
    assert.equal(attributes.get("aria-expanded"), "false");
  }
  cleanup();
  assert.equal(attributes.has("aria-expanded"), false);
});

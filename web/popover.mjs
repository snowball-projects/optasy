let active = null;
let nextId = 0;
const attachments = new WeakMap();
const FOCUSABLE =
  'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])';

// Fixed viewport coordinates keep a report visible outside narrow, scrolling tiles.
export function popoverPosition(rect, size, viewport, gap = 10, margin = 12) {
  const leftEdge = (viewport.left || 0) + margin;
  const topEdge = (viewport.top || 0) + margin;
  const rightEdge = (viewport.left || 0) + viewport.width - margin;
  const bottomEdge = (viewport.top || 0) + viewport.height - margin;
  const maxWidth = Math.max(0, rightEdge - leftEdge);
  const width = Math.min(size.width, maxWidth);
  const below = Math.max(0, bottomEdge - rect.bottom - gap);
  const above = Math.max(0, rect.top - gap - topEdge);
  const placement = below >= size.height || below >= above ? "bottom" : "top";
  const maxHeight = Math.min(
    Math.max(0, bottomEdge - topEdge),
    placement === "bottom" ? below : above,
  );
  const height = Math.min(size.height, maxHeight);
  return {
    left: Math.min(Math.max(rect.left, leftEdge), rightEdge - width),
    top:
      placement === "bottom"
        ? Math.max(topEdge, rect.bottom + gap)
        : Math.max(topEdge, rect.top - gap - height),
    maxWidth,
    maxHeight,
    placement,
  };
}

function viewport() {
  const view = window.visualViewport;
  return {
    left: view?.offsetLeft || 0,
    top: view?.offsetTop || 0,
    width: view?.width || document.documentElement.clientWidth,
    height: view?.height || document.documentElement.clientHeight,
  };
}

export function isPopoverOpen() {
  return Boolean(active);
}

function visibleTriggerRect(trigger, view) {
  const rect = trigger.getBoundingClientRect();
  let left = Math.max(rect.left, view.left);
  let right = Math.min(rect.right, view.left + view.width);
  let top = Math.max(rect.top, view.top);
  let bottom = Math.min(rect.bottom, view.top + view.height);
  for (
    let parent = trigger.parentElement;
    parent;
    parent = parent.parentElement
  ) {
    const style = getComputedStyle(parent);
    const bounds = parent.getBoundingClientRect();
    if (/(auto|scroll|hidden|clip)/.test(style.overflowX)) {
      left = Math.max(left, bounds.left);
      right = Math.min(right, bounds.right);
    }
    if (/(auto|scroll|hidden|clip)/.test(style.overflowY)) {
      top = Math.max(top, bounds.top);
      bottom = Math.min(bottom, bounds.bottom);
    }
  }
  return right > left && bottom > top ? rect : null;
}

export function refreshPopover(event) {
  if (!active) return;
  // Scrolling a long panel must not temporarily enlarge it and clamp scrollTop.
  if (
    event?.type === "scroll" &&
    event.target instanceof Node &&
    active.panel.contains(event.target)
  )
    return;
  if (!active.trigger.isConnected) {
    dismissPopover();
    return;
  }
  const { panel, trigger } = active;
  const view = viewport();
  const rect = visibleTriggerRect(trigger, view);
  if (!rect) {
    dismissPopover();
    return;
  }
  const scrollTop = panel.scrollTop;
  panel.style.maxWidth = `${Math.max(0, view.width - 24)}px`;
  panel.style.maxHeight = `${Math.max(0, view.height - 24)}px`;
  // A gap would cross the next dense injury row and open that row instead.
  const position = popoverPosition(
    rect,
    panel.getBoundingClientRect(),
    view,
    0,
  );
  panel.style.left = `${position.left}px`;
  panel.style.top = `${position.top}px`;
  panel.style.maxHeight = `${position.maxHeight}px`;
  panel.dataset.placement = position.placement;
  panel.scrollTop = scrollTop;
}

function focusableWithin(parent) {
  return [...parent.querySelectorAll(FOCUSABLE)].filter(
    (element) =>
      !element.disabled &&
      element.tabIndex >= 0 &&
      element.getClientRects().length,
  );
}

function nextControl(trigger) {
  const controls = focusableWithin(document).filter(
    (element) => !active.panel.contains(element),
  );
  return controls[controls.indexOf(trigger) + 1];
}

function requestClose(record) {
  clearTimeout(record.closeTimer);
  record.closeTimer = setTimeout(() => {
    if (
      active === record &&
      !record.pinned &&
      !record.hovered &&
      !record.panelHovered &&
      document.activeElement !== record.trigger &&
      !record.panel.contains(document.activeElement)
    ) {
      dismissPopover();
    }
  }, 180);
}

function onOutsidePointer(event) {
  if (
    active &&
    !active.trigger.contains(event.target) &&
    !active.panel.contains(event.target)
  ) {
    dismissPopover();
  }
}

function onKeydown(event) {
  if (!active) return;
  const { trigger, panel } = active;
  if (event.key === "Escape") {
    event.preventDefault();
    const restoreFocus = panel.contains(document.activeElement);
    dismissPopover();
    if (restoreFocus && trigger.isConnected) trigger.focus();
    return;
  }
  if (event.key !== "Tab") return;
  const controls = focusableWithin(panel);
  if (document.activeElement === trigger && !event.shiftKey) {
    event.preventDefault();
    (controls[0] || panel).focus();
  } else if (panel.contains(document.activeElement)) {
    if (
      event.shiftKey &&
      (document.activeElement === controls[0] ||
        document.activeElement === panel)
    ) {
      event.preventDefault();
      trigger.focus();
    } else if (
      !event.shiftKey &&
      (document.activeElement === controls.at(-1) || !controls.length)
    ) {
      const next = nextControl(trigger);
      if (next) {
        event.preventDefault();
        dismissPopover();
        next.focus();
      }
    }
  }
}

function onFocusChange(event) {
  if (
    active &&
    !active.trigger.contains(event.target) &&
    !active.panel.contains(event.target)
  ) {
    dismissPopover();
  }
}

function openPopover(record) {
  if (active === record || record.suppressed || !record.trigger.isConnected)
    return;
  dismissPopover();
  const panel = document.createElement("div");
  panel.id = record.id;
  panel.className = "popover";
  panel.tabIndex = -1;
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", record.label);
  panel.style.position = "fixed";
  panel.style.overflow = "auto";
  panel.style.left = "0px";
  panel.style.top = "0px";
  panel.append(
    typeof record.content === "function" ? record.content() : record.content,
  );
  record.panel = panel;
  record.pinned = false;
  record.panelHovered = false;
  active = record;
  document.body.append(panel);
  record.trigger.setAttribute("aria-expanded", "true");
  panel.addEventListener("pointerenter", () => {
    record.panelHovered = true;
    clearTimeout(record.closeTimer);
  });
  panel.addEventListener("pointerleave", () => {
    record.panelHovered = false;
    requestClose(record);
  });
  panel.addEventListener("focusout", () => requestClose(record));
  record.observer = new MutationObserver(() => {
    if (!record.trigger.isConnected) dismissPopover();
  });
  record.observer.observe(document.body, { childList: true, subtree: true });
  window.addEventListener("resize", refreshPopover);
  window.addEventListener("scroll", refreshPopover, true);
  window.visualViewport?.addEventListener("resize", refreshPopover);
  window.visualViewport?.addEventListener("scroll", refreshPopover);
  document.addEventListener("pointerdown", onOutsidePointer, true);
  document.addEventListener("keydown", onKeydown, true);
  document.addEventListener("focusin", onFocusChange);
  refreshPopover();
}

export function dismissPopover() {
  if (!active) return;
  const record = active;
  active = null;
  record.suppressed = true;
  record.pinned = false;
  clearTimeout(record.closeTimer);
  record.observer.disconnect();
  record.trigger.setAttribute("aria-expanded", "false");
  record.panel.remove();
  record.panel = null;
  window.removeEventListener("resize", refreshPopover);
  window.removeEventListener("scroll", refreshPopover, true);
  window.visualViewport?.removeEventListener("resize", refreshPopover);
  window.visualViewport?.removeEventListener("scroll", refreshPopover);
  document.removeEventListener("pointerdown", onOutsidePointer, true);
  document.removeEventListener("keydown", onKeydown, true);
  document.removeEventListener("focusin", onFocusChange);
}

export function attachPopover(trigger, content, { id, label } = {}) {
  attachments.get(trigger)?.();
  const record = {
    trigger,
    content,
    id: id || `popover-${++nextId}`,
    label: label || trigger.getAttribute("aria-label") || "Details",
    suppressed: false,
    hovered: false,
    panelHovered: false,
    pinned: false,
  };
  trigger.setAttribute("aria-haspopup", "dialog");
  trigger.setAttribute("aria-controls", record.id);
  trigger.setAttribute("aria-expanded", "false");
  const handlers = {
    pointerenter(event) {
      if (event.pointerType === "touch") return;
      record.hovered = true;
      record.suppressed = false;
      clearTimeout(record.closeTimer);
      openPopover(record);
    },
    pointerleave() {
      record.hovered = false;
      requestClose(record);
    },
    focus() {
      openPopover(record);
    },
    blur() {
      record.suppressed = false;
      requestClose(record);
    },
    click() {
      if (active === record && record.pinned) {
        dismissPopover();
      } else {
        record.suppressed = false;
        openPopover(record);
        if (active === record) record.pinned = true;
      }
    },
  };
  for (const [type, handler] of Object.entries(handlers))
    trigger.addEventListener(type, handler);
  const cleanup = () => {
    if (active === record) dismissPopover();
    clearTimeout(record.closeTimer);
    for (const [type, handler] of Object.entries(handlers))
      trigger.removeEventListener(type, handler);
    trigger.removeAttribute("aria-haspopup");
    trigger.removeAttribute("aria-controls");
    trigger.removeAttribute("aria-expanded");
    attachments.delete(trigger);
  };
  attachments.set(trigger, cleanup);
  return cleanup;
}

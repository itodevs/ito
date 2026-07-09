export class VrUi {
  constructor(root, textResources) {
    this.root = root;
    this.text = textResources;
  }

  clear() {
    this.root.replaceChildren();
  }

  panel({ title, subtitle = "", width = 3.2, height = 2.2, position = "0 1.55 -2.4" }) {
    this.clear();
    const panel = document.createElement("a-entity");
    panel.setAttribute("position", position);
    panel.setAttribute("data-ito-panel", "true");
    this.root.appendChild(panel);

    const back = plane({ width, height, color: "#101820", opacity: 0.92 });
    back.setAttribute("position", `0 0 ${-0.01}`);
    panel.appendChild(back);

    panel.appendChild(textEntity(title, { x: -width / 2 + 0.18, y: height / 2 - 0.24, z: 0.01 }, 0.16, "#f7fbff"));
    if (subtitle) {
      panel.appendChild(textEntity(subtitle, { x: -width / 2 + 0.18, y: height / 2 - 0.48, z: 0.01 }, 0.085, "#b8c7d9"));
    }
    return panel;
  }

  button(parent, { label, position, width = 0.82, height = 0.24, enabled = true, action, detail = null }) {
    const button = document.createElement("a-entity");
    button.setAttribute("position", position);
    button.classList.toggle("ito-clickable", enabled);
    button.setAttribute("data-action", action || "");
    button.itoActionDetail = detail;

    const background = plane({
      width,
      height,
      color: enabled ? "#2f8f83" : "#3a4652",
      opacity: 0.96,
    });
    button.appendChild(background);
    button.appendChild(textEntity(label, { x: 0, y: -0.032, z: 0.015 }, 0.075, "#ffffff", "center", width - 0.08));
    parent.appendChild(button);
    return button;
  }

  label(parent, label, position, options = {}) {
    const entity = textEntity(
      label,
      toPosition(position),
      options.size || 0.075,
      options.color || "#dce8f3",
      options.align || "left",
      options.width || 2.6,
    );
    parent.appendChild(entity);
    return entity;
  }
}

export function plane({ width, height, color, opacity = 1 }) {
  const entity = document.createElement("a-plane");
  entity.setAttribute("width", width);
  entity.setAttribute("height", height);
  entity.setAttribute("color", color);
  entity.setAttribute("opacity", opacity);
  entity.setAttribute("shader", "flat");
  return entity;
}

export function textEntity(value, position, size, color, align = "left", width = 2.6) {
  const entity = document.createElement("a-text");
  entity.setAttribute("value", value);
  entity.setAttribute("position", `${position.x} ${position.y} ${position.z}`);
  entity.setAttribute("align", align);
  entity.setAttribute("anchor", align);
  entity.setAttribute("baseline", "top");
  entity.setAttribute("width", width);
  entity.setAttribute("wrap-count", Math.max(12, Math.floor(width / size) * 7));
  entity.setAttribute("color", color);
  entity.setAttribute("shader", "msdf");
  return entity;
}

function toPosition(position) {
  if (typeof position === "string") {
    const [x, y, z] = position.split(/\s+/).map(Number);
    return { x, y, z };
  }
  return position;
}

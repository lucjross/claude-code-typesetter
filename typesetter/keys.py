"""Translate browser KeyboardEvent fields into terminal input bytes."""

CSI = "\x1b["
SS3 = "\x1bO"

# key -> (final char, uses SS3 in application-cursor mode)
CURSOR = {
    "ArrowUp": "A", "ArrowDown": "B", "ArrowRight": "C", "ArrowLeft": "D",
    "Home": "H", "End": "F",
}
TILDE = {
    "Insert": 2, "Delete": 3, "PageUp": 5, "PageDown": 6,
    "F5": 15, "F6": 17, "F7": 18, "F8": 19,
    "F9": 20, "F10": 21, "F11": 23, "F12": 24,
}
SS3_FN = {"F1": "P", "F2": "Q", "F3": "R", "F4": "S"}
CTRL_PUNCT = {" ": "\x00", "@": "\x00", "[": "\x1b", "\\": "\x1c",
              "]": "\x1d", "^": "\x1e", "_": "\x1f", "/": "\x1f"}


def _mod(shift, alt, ctrl):
    return 1 + shift + 2 * alt + 4 * ctrl


def encode(key, ctrl=False, alt=False, shift=False, app_cursor=False):
    """Return the bytes to send to the PTY, or None if the key is ignored."""
    mod = _mod(shift, alt, ctrl)

    if key in CURSOR:
        final = CURSOR[key]
        if mod > 1:
            return f"{CSI}1;{mod}{final}"
        return (SS3 if app_cursor else CSI) + final
    if key in TILDE:
        n = TILDE[key]
        return f"{CSI}{n};{mod}~" if mod > 1 else f"{CSI}{n}~"
    if key in SS3_FN:
        return f"{CSI}1;{mod}{SS3_FN[key]}" if mod > 1 else SS3 + SS3_FN[key]

    if key == "Enter":
        # Claude Code treats ESC CR (meta+enter) as "insert newline".
        return "\x1b\r" if (shift or alt) else "\r"
    if key == "Tab":
        return f"{CSI}Z" if shift else "\t"
    if key == "Backspace":
        if ctrl:
            return "\x17"
        return "\x1b\x7f" if alt else "\x7f"
    if key == "Escape":
        return "\x1b"

    if len(key) != 1:
        return None  # Shift, Control, CapsLock, unidentified, ...

    if ctrl:
        lower = key.lower()
        if "a" <= lower <= "z":
            out = chr(ord(lower) - 96)
        elif key in CTRL_PUNCT:
            out = CTRL_PUNCT[key]
        else:
            return None
        return "\x1b" + out if alt else out
    return "\x1b" + key if alt else key

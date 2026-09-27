// Small, quiet easter eggs. Batman-flavored status lines that rotate.
// Nothing loud — they read like a terminal that happens to have a personality.

export const WATCH_QUOTES = [
  "It's not who I am underneath, but what I do that defines me.",
  "The night is darkest just before the dawn.",
  "I am the shadow that watches the model.",
  "Criminals are a superstitious and cowardly lot.",
  "Everything's impossible until somebody does it.",
  "I never said thank you. — And you'll never have to.",
];

export const IDLE_LINES = [
  "All quiet in Gotham.",
  "The city sleeps. The watch does not.",
  "No threats on the wire.",
  "Standing by.",
];

export function pick(arr, seed = Date.now()) {
  return arr[Math.floor((seed / 5000) % arr.length)];
}

// Konami-ish: type "bat" to flash the signal. Returns a cleanup fn.
export function armSignalEgg(onTrigger) {
  let buf = "";
  const handler = (e) => {
    buf = (buf + e.key.toLowerCase()).slice(-3);
    if (buf === "bat") onTrigger();
  };
  window.addEventListener("keydown", handler);
  return () => window.removeEventListener("keydown", handler);
}

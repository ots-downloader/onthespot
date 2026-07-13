type Dictionary = Record<string, string>;

const localeModules = import.meta.glob<Dictionary>("../locales/*.json", {
  eager: true,
  import: "default",
});

const dictionaries: Record<string, Dictionary> = Object.fromEntries(
  Object.entries(localeModules).map(([path, dictionary]) => [path.match(/\/([^/]+)\.json$/)?.[1] || "", dictionary]),
);

const localeFile = (locale: string) => {
  const language = locale.replace("_", "-");
  if (language.startsWith("zh-CN")) return "zh-CN";
  if (language.startsWith("zh-TW")) return "zh-TW";
  return language.split("-")[0];
};

/**
 * Applies checked-in UI translations after React has rendered.  The original
 * English nodes are retained so switching languages is reversible without a
 * page reload.  No text leaves the browser at runtime.
 */
export const installDocumentLocalization = (locale: string): (() => void) => {
  const dictionary = dictionaries[localeFile(locale)] || {};
  const originals = new WeakMap<Text, string>();
  const attributeOriginals = new WeakMap<Element, Map<string, string>>();

  const translateText = (node: Text) => {
    const parent = node.parentElement;
    if (!parent || parent.closest("script, style, [data-ots-no-translate]")) return;
    const original = originals.get(node) ?? node.nodeValue ?? "";
    originals.set(node, original);
    const translated = dictionary[original.trim()];
    if (!translated || translated === original.trim()) return;
    const leading = original.match(/^\s*/)?.[0] || "";
    const trailing = original.match(/\s*$/)?.[0] || "";
    const next = `${leading}${translated}${trailing}`;
    if (node.nodeValue !== next) node.nodeValue = next;
  };

  const localize = (root: Node) => {
    if (root.nodeType === Node.TEXT_NODE) translateText(root as Text);
    if (root.nodeType === Node.ELEMENT_NODE) {
      const element = root as Element;
      if (!element.closest("[data-ots-no-translate]")) {
        for (const attribute of ["placeholder", "title", "aria-label"]) {
          const current = element.getAttribute(attribute);
          if (!current) continue;
          const values = attributeOriginals.get(element) || new Map<string, string>();
          const original = values.get(attribute) || current;
          values.set(attribute, original);
          attributeOriginals.set(element, values);
          const translated = dictionary[original.trim()];
          if (translated && translated !== original.trim()) element.setAttribute(attribute, translated);
        }
      }
    }
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let current: Node | null;
    while ((current = walker.nextNode())) translateText(current as Text);
  };

  localize(document.body);
  const observer = new MutationObserver((records) => {
    for (const record of records) {
      if (record.type === "characterData") translateText(record.target as Text);
      for (const node of record.addedNodes) localize(node);
    }
  });
  observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  return () => observer.disconnect();
};

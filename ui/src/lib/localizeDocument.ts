type Dictionary = Record<string, string>;

const localeModules = import.meta.glob<Dictionary>("../locales/*.json", {
  import: "default",
});

const localeLoaders: Record<string, () => Promise<Dictionary>> = Object.fromEntries(
  Object.entries(localeModules).map(([path, loader]) => [path.match(/\/([^/]+)\.json$/)?.[1] || "", loader]),
);

type LocalizedValue = {
  original: string;
  applied: string;
};

// These maps intentionally outlive an individual React effect. Recreating
// them on every language change loses the English source text and leaves parts
// of the previous language behind when switching back to English.
const textValues = new WeakMap<Text, LocalizedValue>();
const attributeValues = new WeakMap<Element, Map<string, LocalizedValue>>();

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
  let dictionary: Dictionary = {};
  let observer: MutationObserver | null = null;
  let cancelled = false;

  const localizedValue = (original: string) => {
    const trimmed = original.trim();
    const translated = dictionary[trimmed] || trimmed;
    const leading = original.match(/^\s*/)?.[0] || "";
    const trailing = original.match(/\s*$/)?.[0] || "";
    return `${leading}${translated}${trailing}`;
  };

  const translateText = (node: Text) => {
    const parent = node.parentElement;
    if (!parent || parent.closest("script, style, [data-ots-no-translate]")) return;

    const current = node.nodeValue ?? "";
    let value = textValues.get(node);
    if (!value) {
      value = { original: current, applied: current };
      textValues.set(node, value);
    } else if (current !== value.applied) {
      // React or another application update changed this node. Treat the new
      // value as source text so dynamic counters and statuses are not reverted.
      value.original = current;
    }

    const next = localizedValue(value.original);
    value.applied = next;
    if (node.nodeValue !== next) node.nodeValue = next;
  };

  const translateAttributes = (element: Element) => {
    if (element.closest("[data-ots-no-translate]")) return;

    const values = attributeValues.get(element) || new Map<string, LocalizedValue>();
    attributeValues.set(element, values);
    for (const attribute of ["placeholder", "title", "aria-label"]) {
      const current = element.getAttribute(attribute);
      if (!current) continue;

      let value = values.get(attribute);
      if (!value) {
        value = { original: current, applied: current };
        values.set(attribute, value);
      } else if (current !== value.applied) {
        value.original = current;
      }

      const next = localizedValue(value.original);
      value.applied = next;
      if (current !== next) element.setAttribute(attribute, next);
    }
  };

  const localize = (root: Node) => {
    if (root.nodeType === Node.TEXT_NODE) translateText(root as Text);
    if (root.nodeType === Node.ELEMENT_NODE) translateAttributes(root as Element);

    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    let current: Node | null;
    while ((current = walker.nextNode())) {
      if (current.nodeType === Node.TEXT_NODE) translateText(current as Text);
      else translateAttributes(current as Element);
    }
  };

  const start = async () => {
    const loader = localeLoaders[localeFile(locale)];
    try {
      dictionary = loader ? await loader() : {};
    } catch (error) {
      console.warn(`Could not load the ${locale} language pack; using English.`, error);
      dictionary = {};
    }
    if (cancelled) return;

    localize(document.body);
    observer = new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === "characterData") translateText(record.target as Text);
        for (const node of record.addedNodes) localize(node);
      }
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  };

  void start();
  return () => {
    cancelled = true;
    observer?.disconnect();
  };
};

/**
 * Locale options, shared verbatim with the other 3m4 apps (canonical source:
 * kinegrama/src/i18n/index.svelte.js, mirrored in 3m4-info). One entry per
 * country with that country"s official language. Keep the lists in sync.
 */
export interface LangInfo {
  code: string;
  flag: string;
  name: string;
  alias: string;
}

export const LANGS: LangInfo[] = [
  { code: "es-MX", flag: "🇲🇽", name: "Español (México)", alias: "spanish espanol mexico" },
  { code: "es-ES", flag: "🇪🇸", name: "Español (España)", alias: "spanish espanol espana spain" },
  { code: "es-CO", flag: "🇨🇴", name: "Español (Colombia)", alias: "spanish espanol colombia" },
  { code: "es-AR", flag: "🇦🇷", name: "Español (Argentina)", alias: "spanish espanol argentina" },
  { code: "es-CL", flag: "🇨🇱", name: "Español (Chile)", alias: "spanish espanol chile" },
  { code: "es-PE", flag: "🇵🇪", name: "Español (Perú)", alias: "spanish espanol peru" },
  { code: "en-US", flag: "🇺🇸", name: "English (US)", alias: "english ingles estados unidos usa united states" },
  { code: "en-GB", flag: "🇬🇧", name: "English (UK)", alias: "english ingles reino unido uk united kingdom" },
  { code: "en-CA", flag: "🇨🇦", name: "English (Canada)", alias: "english ingles canada" },
  { code: "en-AU", flag: "🇦🇺", name: "English (Australia)", alias: "english ingles australia" },
  { code: "en-NZ", flag: "🇳🇿", name: "English (New Zealand)", alias: "english ingles nueva zelanda new zealand" },
  { code: "fr-FR", flag: "🇫🇷", name: "Français (France)", alias: "french frances francia france" },
  { code: "de-DE", flag: "🇩🇪", name: "Deutsch (Deutschland)", alias: "german aleman alemania germany" },
  { code: "de-AT", flag: "🇦🇹", name: "Deutsch (Österreich)", alias: "german aleman austria" },
  { code: "it-IT", flag: "🇮🇹", name: "Italiano (Italia)", alias: "italian italiano italia italy" },
  { code: "pt-BR", flag: "🇧🇷", name: "Português (Brasil)", alias: "portuguese portugues brasil brazil" },
  { code: "pt-PT", flag: "🇵🇹", name: "Português (Portugal)", alias: "portuguese portugues portugal" },
  { code: "nl-NL", flag: "🇳🇱", name: "Nederlands (Nederland)", alias: "dutch neerlandes holandes paises bajos netherlands" },
  { code: "sv-SE", flag: "🇸🇪", name: "Svenska (Sverige)", alias: "swedish sueco suecia sweden" },
  { code: "pl-PL", flag: "🇵🇱", name: "Polski (Polska)", alias: "polish polaco polonia poland" },
  { code: "cs-CZ", flag: "🇨🇿", name: "Čeština (Česko)", alias: "czech checo chequia czechia" },
  { code: "ro-RO", flag: "🇷🇴", name: "Română (România)", alias: "romanian rumano rumania romania" },
  { code: "el-GR", flag: "🇬🇷", name: "Ελληνικά (Ελλάδα)", alias: "greek griego grecia greece" },
  { code: "uk-UA", flag: "🇺🇦", name: "Українська (Україна)", alias: "ukrainian ucraniano ucrania ukraine" },
  { code: "ru-RU", flag: "🇷🇺", name: "Русский (Россия)", alias: "russian ruso rusia russia" },
  { code: "tr-TR", flag: "🇹🇷", name: "Türkçe (Türkiye)", alias: "turkish turco turquia turkey" },
  { code: "ar-SA", flag: "🇸🇦", name: "العربية (السعودية)", alias: "arabic arabe arabia saudita saudi arabia" },
  { code: "hi-IN", flag: "🇮🇳", name: "हिन्दी (भारत)", alias: "hindi india" },
  { code: "zh-CN", flag: "🇨🇳", name: "中文（中国）", alias: "chinese chino china mandarin" },
  { code: "ja-JP", flag: "🇯🇵", name: "日本語（日本）", alias: "japanese japones japon japan" },
  { code: "ko-KR", flag: "🇰🇷", name: "한국어 (대한민국)", alias: "korean coreano corea korea" },
  { code: "vi-VN", flag: "🇻🇳", name: "Tiếng Việt (Việt Nam)", alias: "vietnamese vietnamita vietnam" },
  { code: "id-ID", flag: "🇮🇩", name: "Bahasa Indonesia (Indonesia)", alias: "indonesian indonesio indonesia" },
  { code: "th-TH", flag: "🇹🇭", name: "ไทย (ประเทศไทย)", alias: "thai tailandes tailandia thailand" },
];

export const RTL_LANGS = ["ar"];
export const DEFAULT_LANG = "en-US";
export const LANG_STORAGE_KEY = "3m4.lang";

export function baseOf(code: string): string {
  return code.slice(0, 2);
}

export function isRtl(code: string): boolean {
  return RTL_LANGS.includes(baseOf(code));
}

/** Pick the active locale from a saved value and the browser language. */
export function resolveLang(saved: string | null, navigatorLang: string | undefined): string {
  if (saved) {
    if (LANGS.some((l) => l.code === saved)) return saved;
    const migrated = LANGS.find((l) => l.code.startsWith(saved));
    if (migrated) return migrated.code;
  }
  const nav = navigatorLang || DEFAULT_LANG;
  if (LANGS.some((l) => l.code === nav)) return nav;
  const base = baseOf(nav);
  return LANGS.find((l) => l.code.startsWith(base))?.code ?? DEFAULT_LANG;
}

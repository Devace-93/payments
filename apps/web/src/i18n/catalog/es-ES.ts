import type { PartialCatalog } from "./en";

/** Español (España) — overrides vs the neutral Latin-American base. */
const esES: PartialCatalog = {
  "nav.signup": "Registrarse",
  "auth.signUp": "Regístrate",
  "auth.handle": "Nombre de usuario",
  "auth.handleHint": "De 3 a 32 letras minúsculas, dígitos y guiones. Tu nombre público en las apps de 3m4.",
  "auth.err.invalid_handle": "El nombre de usuario debe tener de 3 a 32 letras minúsculas, dígitos o guiones.",
  "auth.err.reserved_handle": "Ese nombre de usuario está reservado. Elige otro.",
  "auth.err.handle_taken": "Ese nombre de usuario ya está ocupado.",
  "profile.handleWarning": "Cambiar tu nombre de usuario cambia tus URL públicas de smart-docs. Los enlaces antiguos dejarán de funcionar.",
  "profile.providersBody": "Inicia sesión con cualquiera de ellas. Vincular nunca cambia tu correo ni tu nombre de usuario.",
  "profile.avatarUpload": "Subir imagen",
  "profile.sessionsBody": "Todos los dispositivos donde tienes la sesión iniciada. Cerrar una tarda menos de un minuto en aplicarse.",
};
export default esES;

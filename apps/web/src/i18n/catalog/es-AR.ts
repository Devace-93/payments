import type { PartialCatalog } from "./en";

/** Español (Argentina) — overrides vs the neutral Latin-American base (voseo). */
const esAR: PartialCatalog = {
  "nav.signup": "Registrate",
  "auth.signUp": "Registrate",
  "auth.noAccount": "¿Todavía no tenés cuenta?",
  "auth.haveAccount": "¿Ya tenés cuenta?",
  "auth.signupTitle": "Creá tu cuenta",
  "auth.magicBody": "Escribí tu correo y te enviaremos un enlace para iniciar sesión sin contraseña.",
  "auth.magicSentTitle": "Revisá tu bandeja de entrada",
  "auth.verifyTitle": "Verificá tu correo",
  "auth.verifyCheckInbox": "Enviamos un enlace de verificación a {email}. Abrilo para desbloquear todas las apps de 3m4. Caduca en 24 horas.",
  "auth.verifyNeedLogin": "Iniciá sesión para reenviar el correo de verificación.",
  "auth.err.invalid_email": "Escribí un correo electrónico válido.",
  "auth.err.reserved_handle": "Ese usuario está reservado. Elegí otro.",
  "auth.err.email_taken": "Ya existe una cuenta con ese correo. Iniciá sesión.",
  "auth.err.generic": "Algo salió mal. Intentá de nuevo.",
  "auth.err.network": "No se pudo contactar al servidor. Revisá tu conexión e intentá de nuevo.",
  "auth.err.rate_limited": "Demasiados intentos. Esperá un momento e intentá de nuevo.",
  "auth.err.session_expired": "Tu sesión caducó. Iniciá sesión de nuevo.",
  "auth.err.invalid_refresh": "Tu sesión caducó. Iniciá sesión de nuevo.",
  "profile.noPassword": "Iniciás sesión con una cuenta vinculada o enlaces mágicos. Definí una contraseña para entrar también con ella.",
  "profile.providersBody": "Iniciá sesión con cualquiera de ellas. Vincular nunca cambia tu correo ni tu usuario.",
};
export default esAR;

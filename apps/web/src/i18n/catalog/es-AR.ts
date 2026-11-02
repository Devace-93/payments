import type { PartialCatalog } from "./en";

/** Español (Argentina) — overrides vs the neutral Latin-American base (voseo). */
const esAR: PartialCatalog = {
  "pay.pickApp": "Elegí una app",
  "pay.treat.coffee.title": "Invitale un café a Enrique ☕",
  "pay.treat.coffee.lede": "Un café de una sola vez para {app}. Se paga con tarjeta a través de Stripe; no necesitás cuenta.",
  "pay.treat.beer.title": "Invitale una cerveza a Enrique 🍺",
  "pay.treat.beer.lede": "Una cerveza de una sola vez para {app}. Se paga con tarjeta a través de Stripe; no necesitás cuenta.",
  "pay.publicToggle": "Mostrar mi nombre públicamente como patrocinador",
  "pay.claimExplainer": "¿Pagás como invitado? Tu recibo incluye un código para vincular la donación a una cuenta de 3m4 más adelante.",
  "pay.subscribeTitle": "Suscribite a {app}",
  "pay.subscribeSubtitle": "Stripe hace el cobro. Cancelá cuando quieras desde tu página de apoyo.",
  "pay.successPendingBody": "Tu pago va en camino. Revisá tu correo para ver el recibo o volvé en un minuto.",
  "pay.thanksGuestBody": "Te enviamos por correo un recibo con un código. Creá una cuenta o iniciá sesión para vincular esta donación y obtener tu insignia de patrocinador.",
  "pay.closeHint": "Ya podés cerrar esta ventana.",
  "pay.cancelBody": "No se cobró nada. Podés intentarlo de nuevo cuando quieras.",
  "pay.claimSubtitle": "Escribí el código de tu recibo para vincular la donación a tu cuenta.",
  "pay.claimLogin": "Iniciá sesión para vincularla",
  "pay.noSubscriptions": "Todavía no tenés suscripciones.",
  "pay.noPayments": "Todavía no hay pagos.",
  "pay.badgeBody": "Mostrala en tu README o en tu sitio. Se actualiza sola.",
  "pay.badgeStable": "La variante /badge/u/… sigue funcionando si cambiás tu usuario.",
  "pay.err.generic": "Algo salió mal. Intentá de nuevo.",
  "pay.err.network": "No se pudo contactar al servidor. Revisá tu conexión e intentá de nuevo.",
  "pay.err.validation_error": "Revisá el formulario e intentá de nuevo.",
  "pay.err.invalid_code": "Ese código no es válido. Compáralo con tu recibo.",
  "pay.err.already_subscribed": "Ya tenés una suscripción activa a esta app.",
  "pay.err.rate_limited": "Demasiados intentos. Esperá un momento e intentá de nuevo.",
  "pay.err.session_expired": "Tu sesión caducó. Iniciá sesión de nuevo.",
  "pay.err.email_unverified": "Primero verificá el correo de tu cuenta de 3m4.",
  "pay.err.forbidden": "No podés hacer eso.",
};
export default esAR;

import type { PartialCatalog } from "./en";

/** Español (España) — overrides vs the neutral Latin-American base. */
const esES: PartialCatalog = {
  "pay.amount": "Importe",
  "pay.customAmount": "Otro importe",
  "pay.donateSubtitle": "Invita a Enrique a un café. Se paga con tarjeta a través de Stripe; no necesitas cuenta.",
  "pay.err.amount_too_large": "Ese importe supera el máximo.",
  "pay.alreadySubscribedCta": "Gestionar tu suscripción",
  "pay.manage": "Gestionar",
  "pay.openingPortal": "Abriendo el portal de facturación…",
  "pay.err.no_customer": "Aún no hay nada que gestionar: tu cuenta no tiene registro de facturación.",
  "pay.badgeStable": "La variante /badge/u/… sigue funcionando si cambias tu nombre de usuario.",
};
export default esES;

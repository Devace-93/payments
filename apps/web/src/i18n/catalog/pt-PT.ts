import type { PartialCatalog } from "./en";

/** Português (Portugal) — overrides vs the Brazilian base. */
const ptPT: PartialCatalog = {
  // chrome
  "nav.me": "O seu apoio",
  "nav.login": "Iniciar sessão",
  "nav.signup": "Criar conta",
  "nav.logout": "Terminar sessão",
  "nav.signedInAs": "Sessão iniciada como @{handle}",

  "ui.search": "Pesquisar",

  "building.title": "Estamos a construir o 3m4 payments",
  "building.body":
    "Um só sítio para apoiar todas as apps 3m4. As páginas ainda não estão abertas, mas a API, os badges e o pay.js continuam a funcionar.",

  "common.loading": "A carregar…",
  "common.save": "Guardar",
  "common.saving": "A guardar…",
  "common.saved": "Guardado.",
  "common.retry": "Tentar novamente",

  // Home / catalog
  "pay.homeTitle": "Apoie as apps 3m4",
  "pay.homeSubtitle": "Donativos, subscrições, recibos e badges de apoiante — um só sítio para todas as apps 3m4.",
  "pay.pickApp": "Escolha uma app",
  "pay.yourSupport": "O seu apoio",
  "pay.yourSupportHint": "Recibos, subscrições e o seu badge.",
  "pay.treat.coffee.title": "Pague um café ao Enrique ☕",
  "pay.treat.coffee.lede": "Um café pontual para a {app}. Pagamento com cartão através do Stripe — sem precisar de conta.",
  "pay.treat.coffee.thanks": "O seu café de {amount} para a {app} foi concluído ☕",
  "pay.treat.beer.title": "Pague uma cerveja ao Enrique 🍺",
  "pay.treat.beer.lede": "Uma cerveja pontual para a {app}. Pagamento com cartão através do Stripe — sem precisar de conta.",
  "pay.treat.beer.thanks": "A sua cerveja de {amount} para a {app} foi concluída 🍺",
  "pay.catalogSubscribe": "Subscrever",
  "pay.noProducts": "A {app} ainda não tem planos — são os donativos que a mantêm viva.",
  "pay.unknownApp": "Não conhecemos essa app.",

  // Donate
  "pay.donateTitle": "Apoie a {app}",
  "pay.donatingAs": "A doar como @{handle}",
  "pay.amount": "Montante",
  "pay.customAmount": "Outro montante",
  "pay.messageHint": "Até 200 caracteres. Aparece ao lado do seu nome se escolher aparecer publicamente.",
  "pay.publicToggle": "Mostrar o meu nome publicamente como apoiante",
  "pay.displayNameHint": "Aparece na lista de apoiantes.",
  "pay.feeHint": "≈ {net} chegam ao Enrique depois das comissões",
  "pay.donateCardBusy": "A abrir o Stripe…",
  "pay.claimExplainer": "Vai pagar sem conta? O seu recibo traz um código de resgate para associar o donativo a uma conta 3m4 mais tarde.",
  "pay.securedByStripe": "Os pagamentos são processados pelo Stripe. Nunca vemos o seu cartão.",

  // Subscribe
  "pay.subscribeTitle": "Subscrever a {app}",
  "pay.subscribeSubtitle": "Cobrado pelo Stripe. Cancele quando quiser na sua página de apoio.",
  "pay.subscribingAs": "A subscrever como @{handle}",
  "pay.alreadySubscribedCta": "Gerir a sua subscrição",
  "pay.loginRequired": "As subscrições precisam de uma conta 3m4. A encaminhar para o início de sessão…",

  // Success
  "pay.successWaiting": "A confirmar o seu pagamento…",
  "pay.successPending": "Ainda à espera do Stripe",
  "pay.successPendingBody": "O seu pagamento está a caminho. Veja o recibo no seu e-mail ou volte daqui a um minuto.",
  "pay.thanksGuestBody": "Enviámos um recibo com um código de resgate para o seu e-mail. Crie uma conta ou inicie sessão para associar este donativo e receber o seu badge de apoiante.",
  "pay.thanksUserBody": "Já está na sua página de apoio.",
  "pay.logIn": "Iniciar sessão",
  "pay.subscribedBody": "A sua subscrição da {app} está ativa.",
  "pay.manage": "Gerir",
  "pay.backTo": "Voltar à {app}",
  "pay.closeHint": "Já pode fechar esta janela.",
  "pay.viewSupport": "Ver o seu apoio",

  // Cancel
  "pay.cancelBody": "Nada foi cobrado. Pode tentar novamente quando quiser.",
  "pay.tryAgain": "Tentar novamente",

  // Claim
  "pay.claimTitle": "Resgatar um donativo",
  "pay.claimSubtitle": "Introduza o código do seu recibo para associar o donativo à sua conta.",
  "pay.claiming": "A resgatar…",
  "pay.claimLogin": "Inicie sessão para o resgatar",
  "pay.claimedTitle": "Donativo resgatado",
  "pay.claimedBody": "O seu donativo de {amount} para a {app} faz agora parte da sua conta.",

  // Me
  "pay.meTitle": "O seu apoio",
  "pay.meSubtitle": "Sessão iniciada como @{handle}",
  "pay.loadFailed": "Não foi possível carregar a sua página de apoio.",
  "pay.subscriptions": "Subscrições",
  "pay.noSubscriptions": "Ainda não há subscrições.",
  "pay.renews": "Renova a {date}",
  "pay.endsOn": "Termina a {date}",
  "pay.openingPortal": "A abrir o portal de faturação…",
  "pay.status.trialing": "Período experimental",
  "pay.status.past_due": "Em atraso",
  "pay.noPayments": "Ainda não há pagamentos.",
  "pay.kind.donation": "Donativo",
  "pay.kind.subscription": "Subscrição",
  "pay.publicSupporter": "Apoiante público",
  "pay.publicSupporterBody": "Mostre o seu nome nas páginas de apoiantes das apps que apoia.",
  "pay.preferredCurrencyBody": "Pré-selecionada em todos os pagamentos.",
  "pay.badge": "Badge de apoiante",
  "pay.badgeBody": "Mostre-o no seu README ou no seu site. Atualiza-se sozinho.",
  "pay.badgeStable": "A variante /badge/u/… continua a funcionar se mudar o seu nome de utilizador.",
  "pay.badgesOff": "Os badges estão desativados de momento.",

  // API error codes
  "pay.err.generic": "Algo correu mal. Tente novamente.",
  "pay.err.network": "Não foi possível contactar o servidor. Verifique a ligação e tente novamente.",
  "pay.err.validation_error": "Verifique o formulário e tente novamente.",
  "pay.err.unknown_app": "Não conhecemos essa app.",
  "pay.err.amount_too_large": "Esse montante está acima do máximo.",
  "pay.err.unsupported_currency": "Essa moeda não é suportada.",
  "pay.err.already_subscribed": "Já tem uma subscrição ativa desta app.",
  "pay.err.invalid_code": "Esse código não é válido. Confirme-o no seu recibo.",
  "pay.err.no_customer": "Ainda não há nada para gerir — não existe registo de faturação na sua conta.",
  "pay.err.rate_limited": "Demasiadas tentativas. Aguarde um momento e tente novamente.",
  "pay.err.no_session": "Não tem sessão iniciada.",
  "pay.err.session_expired": "A sua sessão expirou. Inicie sessão novamente.",
  "pay.err.email_unverified": "Verifique primeiro o e-mail da sua conta 3m4.",
  "pay.err.forbidden": "Não pode fazer isso.",
  "pay.err.feature_off": "Isto está desativado de momento.",
};
export default ptPT;

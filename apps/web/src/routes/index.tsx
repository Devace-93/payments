import type { RequestHandler } from "@builder.io/qwik-city";

/**
 * `/` → `/profile` when a session cookie is present, else `/login`. The
 * cookie's presence is only a hint (the profile page verifies it against the
 * API and bounces to /login on 401), but it lets the redirect happen on the
 * server without a flash of the wrong page.
 */
export const onGet: RequestHandler = ({ cookie, redirect, url }) => {
  const dest = cookie.has("3m4_session") ? "/profile" : "/login";
  throw redirect(302, `${dest}${url.search}`);
};

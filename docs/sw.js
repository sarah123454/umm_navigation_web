// sw.js – macht die App bei schlechtem Netz nutzbar.
// Strategie "erst Netz, dann Speicher": Neue Daten kommen sofort an,
// ohne Netz wird die zuletzt geladene Version aus dem Speicher genommen.
// Bei jeder Änderung an Daten oder Lageplan die Nummer erhöhen!
const SPEICHER = "umm-navigation-v2";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(
  caches.keys()
    .then(namen => Promise.all(namen.filter(n => n !== SPEICHER).map(n => caches.delete(n))))
    .then(() => self.clients.claim())
));

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET" || new URL(req.url).origin !== location.origin) return;
  e.respondWith(
    fetch(req)
      .then(antwort => {
        const kopie = antwort.clone();
        caches.open(SPEICHER).then(c => c.put(req, kopie));
        return antwort;
      })
      .catch(() => caches.match(req, { ignoreSearch: true }))
  );
});
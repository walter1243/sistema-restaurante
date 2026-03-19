self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (_) {
    data = { body: event.data ? event.data.text() : 'Nova entrega disponível.' };
  }

  const title = data.title || 'Entrega';
  const body = data.body || 'Nova entrega disponível.';
  const url = data.url || '/entregador.html';

  event.waitUntil((async () => {
    const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of clients) {
      client.postMessage({
        type: 'delivery-push',
        title,
        body,
        url
      });
    }

    await self.registration.showNotification(title, {
      body,
      tag: data.tag || 'entrega',
      renotify: true,
      requireInteraction: true,
      vibrate: [220, 120, 220],
      data: { url },
      icon: 'https://cdn-icons-png.flaticon.com/512/2972/2972185.png',
      badge: 'https://cdn-icons-png.flaticon.com/512/2972/2972185.png'
    });
  })());
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || '/entregador.html';

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ('focus' in client) {
          try {
            client.navigate(targetUrl);
          } catch (_) {}
          return client.focus();
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl);
      }
      return null;
    })
  );
});

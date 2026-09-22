import { mount } from 'svelte';
import App from './App.svelte';
import './app.css';

if ('serviceWorker' in navigator) {
  if (import.meta.env.PROD) {
    addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));
  } else {
    // A worker left over from a production build on the same origin would keep serving
    // old modules to the dev server. Development never wants one.
    navigator.serviceWorker.getRegistrations().then((regs) => regs.forEach((r) => r.unregister()));
  }
}

export default mount(App, { target: document.getElementById('app')! });

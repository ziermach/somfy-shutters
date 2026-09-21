import { mount } from 'svelte';
import App from './App.svelte';
import './app.css';

if ('serviceWorker' in navigator && import.meta.env.PROD) {
  addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));
}

export default mount(App, { target: document.getElementById('app')! });

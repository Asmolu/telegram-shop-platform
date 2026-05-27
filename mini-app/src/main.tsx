import React from 'react';
import ReactDOM from 'react-dom/client';
import './styles.css';

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1';

function App() {
  return (
    <main className="app-shell">
      <section className="card">
        <p className="eyebrow">Telegram Shop Platform</p>
        <h1>Telegram Shop Mini App</h1>
        <p>
          This is a clean Vite/React placeholder. Implement the UI according to
          SRS.README.md and SPRINT_PLAN.md.
        </p>
        <code>API: {apiBaseUrl}</code>
      </section>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import { getConnectionTelemetry, getViewportTelemetry, initTelemetryClient, trackTelemetry } from './shared/telemetry';
import './styles.css';

initTelemetryClient();
trackTelemetry('mini_app.bootstrap_started', {
  route: window.location.pathname,
  ...getConnectionTelemetry(),
  ...getViewportTelemetry(),
});

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

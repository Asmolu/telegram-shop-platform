import React from 'react';
import { trackTelemetry } from '../telemetry';

type AppErrorBoundaryState = {
  hasError: boolean;
};

export class AppErrorBoundary extends React.Component<
  { children: React.ReactNode; reloadWindow?: () => void },
  AppErrorBoundaryState
> {
  state: AppErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): AppErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error) {
    trackTelemetry('frontend.error_boundary_triggered', {
      route: window.location.pathname,
      error_category: 'render_error',
    }, { priority: 'critical' });
    if (import.meta.env.DEV) {
      console.error(error);
    }
  }

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <section className="route-error-state" role="alert">
        <h2>Что-то пошло не так</h2>
        <p>Приложение столкнулось с ошибкой отображения. Обновите Mini App, чтобы безопасно продолжить.</p>
        <button
          className="primary-button"
          type="button"
          onClick={this.props.reloadWindow ?? (() => window.location.reload())}
        >
          Обновить
        </button>
      </section>
    );
  }
}

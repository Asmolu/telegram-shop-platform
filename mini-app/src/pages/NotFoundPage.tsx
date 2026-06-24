import React from 'react';
import { useRouter } from '../shared/router/RouterProvider';
import { TopBar } from '../shared/ui/AppShell';

export function NotFoundPage() {
  const { navigate } = useRouter();

  return (
    <div className="page">
      <TopBar title="Страница не найдена" backFallback="/main" />
      <section className="state-block">
        <h1>Страница не найдена</h1>
        <button className="primary-button" type="button" onClick={() => navigate('/main')}>
          К товарам
        </button>
      </section>
    </div>
  );
}

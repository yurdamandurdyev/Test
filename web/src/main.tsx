import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './style.css';

class Boundary extends React.Component<React.PropsWithChildren, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? <main className="fatal"><h1>Не удалось отобразить страницу</h1><p>Перезагрузите приложение. Загруженные данные не сохраняются в браузерном хранилище.</p><button onClick={() => location.reload()}>Перезагрузить</button></main> : this.props.children;
  }
}
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><Boundary><App /></Boundary></React.StrictMode>);

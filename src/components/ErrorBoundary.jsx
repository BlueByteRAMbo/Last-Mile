import React from 'react';

// Without this, any render error unmounts the whole app and leaves a blank screen.
export default class ErrorBoundary extends React.Component {
  state = { error: null };

  static getDerivedStateFromError(error) { return { error }; }

  componentDidCatch(error, info) { console.error('UI error:', error, info?.componentStack); }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="w-full h-screen flex flex-col items-center justify-center gap-3 bg-route-base text-white p-6 text-center">
        <h1 className="text-lg font-semibold">Something went wrong on this screen</h1>
        <p className="text-sm text-slate-400 max-w-md">{String(this.state.error?.message || this.state.error)}</p>
        <button onClick={() => window.location.reload()} className="text-sm bg-route-cyan/20 text-route-cyan rounded px-4 py-2 hover:bg-route-cyan/30">
          Reload
        </button>
      </div>
    );
  }
}

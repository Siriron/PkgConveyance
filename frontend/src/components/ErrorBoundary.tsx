import React from 'react';

interface State {
  hasError: boolean;
  message?: string;
}

export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, State> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="shell">
          <div className="empty-state">
            <p>Something went wrong rendering this page.</p>
            <p className="mono form-hint">{this.state.message}</p>
            <a href="/">Back to deals</a>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

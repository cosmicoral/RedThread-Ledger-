import { ReviewQueue } from "./pages/ReviewQueue";

export function App() {
  return (
    <div className="app">
      <header className="app-header">
        <p className="eyebrow">Ylookup × Encode · Product Track</p>
        <h1>RedThread Ledger</h1>
        <p className="lede">
          Evidence-linked bank statement processing. Every proposed journal
          line keeps the source PDF and the master-data row used to make it.
        </p>
      </header>
      <ReviewQueue />
    </div>
  );
}

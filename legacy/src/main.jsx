import React, {useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';

const rows = [
  {id:'SHP-1001', customer:'FreshMart Northeast', product:'Romaine Hearts', facility:'Salinas', status:'Delivered'},
  {id:'SHP-1002', customer:'Harvest Grocers', product:'Baby Spinach', facility:'Yuma', status:'Exception'},
  {id:'SHP-1003', customer:'City Market', product:'Spring Mix', facility:'Salinas', status:'In Transit'},
];
function App() {
  const [query, setQuery] = useState('');
  const result = rows.find(row => row.id.toLowerCase() === query.toLowerCase()) || null;
  return <main><div className="eyebrow">Legacy sample</div><h1>Shipment lookup</h1><p>Read-only React workflow with the same synthetic records used by HarvestOps.</p><input aria-label="Shipment ID" placeholder="SHP-1001" value={query} onChange={e => setQuery(e.target.value.trim())}/>{result ? <section><b>{result.id}</b><div>{result.customer} · {result.product}</div><div>{result.facility} · {result.status}</div></section> : query ? <section>No shipment found.</section> : null}</main>
}
createRoot(document.getElementById('root')).render(<App/>);

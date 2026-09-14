import { useEffect, useState } from "react";
import { Check, Plus } from "lucide-react";
import { api, Catalog, label } from "./api";
import { Field } from "./main";

type Category = { id: number; name: string; kind: string; incident_type: string; active: boolean };
type Group = { id: number; name: string; user_ids: number[] };
type Rule = { category_id: number; strategy: string; group_id: number | null; assignee_id: number | null };

export function RoutingSettings({ catalog, refresh }: { catalog: Catalog; refresh: () => Promise<void> }) {
  const [data, setData] = useState<{ categories: Category[]; groups: Group[]; rules: Rule[] }>({ categories: [], groups: [], rules: [] });
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const load = () => api("/admin/routing").then(setData);
  useEffect(() => { load().catch((e) => setError(e.message)); }, []);
  async function run(action: () => Promise<unknown>, message: string) {
    setError(""); setNotice("");
    try { await action(); await Promise.all([load(), refresh()]); setNotice(message); }
    catch (e) { setError((e as Error).message); }
  }
  return <>
    {error && <div className="error">{error}</div>}
    {notice && <div className="success"><Check size={16}/>{notice}</div>}
    <div className="settings-grid">
      <section className="panel description">
        <h2>Issue categories and types</h2>
        <p className="muted">Categories appear on support tickets; applicable options appear as types when logging internal issues. Bug, Question, and Enhancement are always available. Their classification connects them to SLA reporting.</p>
        <div className="entity-list">{data.categories.map((c) => <div key={c.id}><strong>{c.name}</strong><small>{label(c.incident_type)} · {c.kind}</small></div>)}</div>
        <form onSubmit={(e) => { e.preventDefault(); const f = new FormData(e.currentTarget); run(() => api("/admin/routing/categories", "POST", { name: f.get("name"), kind: f.get("kind"), incident_type: f.get("type"), active: true }), "Category created."); e.currentTarget.reset(); }}>
          <Field label="Category name"><input name="name" required /></Field>
          <div className="form-grid">
            <Field label="Available for"><select name="kind"><option value="both">Tickets and issues</option><option value="support">Support tickets</option><option value="bug">Internal issues</option></select></Field>
            <Field label="SLA classification"><select name="type">{["question","bug","outage","enhancement"].map((v)=><option key={v} value={v}>{label(v)}</option>)}</select></Field>
          </div>
          <button className="primary"><Plus size={16}/>Add category</button>
        </form>
      </section>
      <section className="panel description">
        <h2>Support groups</h2>
        <p className="muted">Group membership supplies agents for round-robin and lowest-volume assignment.</p>
        {data.groups.map((g) => <div key={g.id} className="routing-group"><strong>{g.name}</strong>{catalog.agents.map((a)=><label className="checkbox" key={a.id}><input type="checkbox" checked={g.user_ids.includes(a.id)} onChange={(e)=>run(()=>api(`/admin/routing/groups/${g.id}/members`,"PUT",{user_ids:e.target.checked?[...g.user_ids,a.id]:g.user_ids.filter((id)=>id!==a.id)}),"Group membership updated.")}/>{a.name}</label>)}</div>)}
        <form onSubmit={(e)=>{e.preventDefault();const f=new FormData(e.currentTarget);run(()=>api("/admin/routing/groups","POST",{name:f.get("name"),description:""}),"Support group created.");e.currentTarget.reset();}}><Field label="Group name"><input name="name" required/></Field><button className="primary"><Plus size={16}/>Add group</button></form>
      </section>
    </div>
    <section className="panel description">
      <h2>Assignment rules</h2>
      <p className="muted">Manual leaves the ticket in its category queue. Fixed selects one person. Round robin rotates through a group. Lowest volume selects the group member with the fewest open tickets and issues.</p>
      <div className="table-scroll"><table><thead><tr><th>Category</th><th>Strategy</th><th>Target</th></tr></thead><tbody>{data.categories.filter(c=>c.active).map((c)=>{const rule=data.rules.find(r=>r.category_id===c.id)||{category_id:c.id,strategy:"manual",group_id:null,assignee_id:null};const save=(next:Rule)=>run(()=>api("/admin/routing/rules","PUT",next),"Assignment rule saved.");return <tr key={c.id}><td>{c.name}</td><td><select value={rule.strategy} onChange={(e)=>save({...rule,strategy:e.target.value,group_id:["round_robin","least_open"].includes(e.target.value)?data.groups[0]?.id||null:null,assignee_id:e.target.value==="fixed"?catalog.agents[0]?.id||null:null})}><option value="manual">Manual queue</option><option value="fixed">Always assign</option><option value="round_robin">Round robin</option><option value="least_open">Lowest open volume</option></select></td><td>{rule.strategy==="fixed"?<select value={rule.assignee_id||""} onChange={(e)=>save({...rule,assignee_id:Number(e.target.value)})}>{catalog.agents.map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select>:rule.strategy!=="manual"?<select value={rule.group_id||""} onChange={(e)=>save({...rule,group_id:Number(e.target.value)})}>{data.groups.map(g=><option key={g.id} value={g.id}>{g.name}</option>)}</select>:"Category queue"}</td></tr>})}</tbody></table></div>
    </section>
  </>;
}

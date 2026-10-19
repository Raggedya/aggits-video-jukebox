// Test/preview adapter only. Uses the real Worker SQL on a LOCAL SQLite file.
import {DatabaseSync} from 'node:sqlite';
import fs from 'node:fs';
import path from 'node:path';
export function localDatabase(filename=':memory:') {
  const sqlite=new DatabaseSync(filename);sqlite.exec('PRAGMA busy_timeout=5000;');
  for(const name of ['0004_machine_statistics.sql','0005_all_machine_spins.sql','0006_all_machine_details.sql','0007_global_lever_total.sql'])sqlite.exec(fs.readFileSync(path.resolve('worker/migrations',name),'utf8'));
  return {sqlite,DB:{prepare(sql){
    const statement=sqlite.prepare(sql);
    const bound=args=>({async first(){return statement.get(...args)||null},async run(){const r=statement.run(...args);return{meta:{changes:Number(r.changes)}}}});
    return {...bound([]),bind(...args){return bound(args)}};
  }}};
}

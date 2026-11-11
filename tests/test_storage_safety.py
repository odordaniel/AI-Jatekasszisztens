import ast, tempfile, threading, json, unittest
from pathlib import Path
SRC=Path(__file__).resolve().parents[1] / 'src' / 'assistant.py'
tree=ast.parse(SRC.read_text())
funcs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('write_config','load_config')]
class StorageTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
  ns={'_STORAGE_LOCK':threading.RLock(),'CONFIG_PATH':Path(self.tmp.name)/'config.json','json':json,'logging':__import__('logging'),'DEFAULTS':{'model':'default','hotkeys':{}},'normalize_hotkeys':lambda x:x,'read_api_key':lambda:'','save_api_key':lambda x:None,'HOTKEY_DEFAULTS':{}}
  exec(compile(ast.fix_missing_locations(ast.Module(body=funcs,type_ignores=[])),str(SRC),'exec'),ns)
  self.ns=ns
 def test_invalid_json_preserved(self):
  p=self.ns['CONFIG_PATH']; p.write_text('{broken',encoding='utf-8')
  self.assertEqual(self.ns['load_config']()['model'],'default'); self.assertEqual(p.read_text(),'{broken')
 def test_nonobject_json_defaults(self):
  self.ns['CONFIG_PATH'].write_text('[]')
  self.assertEqual(self.ns['load_config']()['model'],'default')
 def test_missing_config_created(self):
  self.assertEqual(self.ns['load_config']()['model'],'default'); self.assertTrue(self.ns['CONFIG_PATH'].exists())
 def test_parallel_writes_valid(self):
  def write(i):
   for _ in range(20): self.ns['write_config']({'model':str(i),'api_key':'secret'})
  threads=[threading.Thread(target=write,args=(i,)) for i in range(8)]
  [t.start() for t in threads]; [t.join() for t in threads]
  data=json.loads(self.ns['CONFIG_PATH'].read_text()); self.assertNotIn('api_key',data); self.assertIn(data['model'],map(str,range(8)))
if __name__=='__main__':unittest.main()

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


class RunnerResumeTests(unittest.TestCase):
    def load_runner(self):
        with patch.dict(sys.modules,{'monitor_stage':__import__('scripts.monitor_stage',fromlist=['Memory'])}):
            spec=importlib.util.spec_from_file_location('ny_runner',Path('scripts/continue_ny_build.py'))
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def test_existing_logs_preserved(self):
        runner=self.load_runner()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);old=root/'ny-import-1.log';old.write_text('preserved')
            with patch.object(runner,'ROOT',root),patch.object(runner,'ready'),patch.object(runner,'atomic_status'),\
                 patch.object(runner.subprocess,'run',return_value=types.SimpleNamespace(returncode=0)) as run:
                runner.stage('ny-import',14400,1100,'import.py')
            self.assertEqual(old.read_text(),'preserved')
            command=run.call_args.args[0]
            self.assertEqual(command[command.index('--log')+1],str(root/'ny-import-2.log'))
            self.assertEqual(command[command.index('--memory-mib')+1],'1100')

    def test_export_retry_rechecks_partial_output(self):
        runner=self.load_runner();exists=False;commands=[]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def run(command):
                nonlocal exists
                commands.append(command)
                if len(commands)==1:
                    exists=True
                    log=Path(command[command.index('--log')+1])
                    log.with_suffix('.resources.json').write_text(json.dumps({'stopped_reason':'System available RAM below 384 MiB'}))
                    return types.SimpleNamespace(returncode=1)
                return types.SimpleNamespace(returncode=0)
            original=Path.exists
            def output_exists(path):
                return exists if str(path).replace('\\','/')=='build/new-york' else original(path)
            with patch.object(runner,'ROOT',root),patch.object(runner,'ready'),patch.object(runner,'atomic_status'),\
                 patch.object(runner.subprocess,'run',side_effect=run),patch.object(Path,'exists',output_exists):
                runner.stage('ny-export',14400,700,'export.py','--archive-staging')
            self.assertNotIn('--resume-export',commands[0])
            self.assertIn('--resume-export',commands[1])


if __name__=='__main__':unittest.main()

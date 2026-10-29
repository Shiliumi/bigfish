import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import fish_embedding_process as client
import setup_semantic_runtime as setup


class EmbeddingProcessTest(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.home=Path(temporary.name)
    def ready(self):
        executable=self.home/'python/mock/bin/python';executable.parent.mkdir(parents=True);executable.write_text('fixture');executable.chmod(0o755)
        python=self.home/'generations'/('a'*32)/'venv/bin/python';python.parent.mkdir(parents=True);python.symlink_to(executable)
        model=self.home/'models'/client.MODEL_SHA;model.mkdir(parents=True)
        value={'protocol':1,'model':client.MODEL_KEY,'python':str(python.relative_to(self.home)),'model_dir':str(model.relative_to(self.home))}
        (self.home/'active.json').write_text(json.dumps(value));return value
    def response(self,ident='a'*32,count=1):
        return {'protocol':1,'id':ident,'model':client.MODEL_KEY,'vectors':[[1.]+[0.]*511 for _ in range(count)]}
    def exchange(self,code,payload=b'fixture',timeout=.3):
        return client._exchange([sys.executable,'-I','-c',code],payload,timeout)
    def test_optional_model_modules_are_not_imported_by_the_parent(self):
        code="import sys;sys.path.insert(0,'scripts');import fish_embedding_process;assert not {'numpy','onnxruntime','tokenizers'}.intersection(sys.modules)"
        self.assertEqual(subprocess.run([sys.executable,'-c',code],capture_output=True).returncode,0)
    def test_both_pipe_directions_are_drained_without_blocking(self):
        payload=b'f'*client.MAX_INPUT
        self.assertEqual(self.exchange('import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())',payload,2),payload)
    def test_stalled_reader_and_writer_are_killed_and_reaped(self):
        processes=[];original=subprocess.Popen
        def launch(*args,**kwargs):
            process=original(*args,**kwargs);processes.append(process);return process
        with patch.object(client.subprocess,'Popen',side_effect=launch):
            started=time.monotonic();self.assertIsNone(self.exchange('import time;time.sleep(20)',b'x'*client.MAX_INPUT,.15))
        self.assertLess(time.monotonic()-started,1.5);self.assertIsNotNone(processes[0].poll())
    def test_partial_response_does_not_escape_a_timeout(self):
        self.assertIsNone(self.exchange("import sys,time;print('{',flush=True);time.sleep(20)",timeout=.15))
    def test_output_size_limit_stops_a_flooding_child(self):
        self.assertIsNone(self.exchange('import sys;sys.stdout.write("x"*600000);sys.stdout.flush()',timeout=2))
    def test_stderr_cannot_fill_a_pipe_or_become_the_response(self):
        self.assertEqual(self.exchange('import sys;sys.stderr.write("x"*600000);sys.stderr.flush();print("ok")',timeout=2),b'ok\n')
    def test_abrupt_exit_is_unavailable(self):
        self.assertIsNone(self.exchange('import os;os._exit(2)',timeout=2))
    def test_worker_does_not_inherit_model_api_credentials(self):
        with patch.dict(os.environ,{'FICTION_MODEL_API_KEY':'fiction-private-value'}):
            self.assertEqual(self.exchange("import os;print(os.getenv('FICTION_MODEL_API_KEY','absent'))",timeout=2),b'absent\n')
    def test_protocol_rejects_wrong_owner_shape_norm_and_nonfinite_vectors(self):
        good=self.response();self.assertEqual(len(client.decode_response(json.dumps(good).encode(),'a'*32,1)),1)
        bad=[{**good,'id':'b'*32},{**good,'model':'wrong'},{**good,'protocol':True},{**good,'vectors':[]},
             {**good,'vectors':[[0.]*512]},{**good,'vectors':[[True]+[0.]*511]},
             {**good,'vectors':[[float('nan')]+[0.]*511]},{**good,'vectors':[[10**1000]+[0.]*511]},{**good,'vectors':[[1.]]}]
        for value in bad:
            with self.subTest(value=str(value)[:50]):
                with self.assertRaises(ValueError):client.decode_response(json.dumps(value).encode(),'a'*32,1)
        with self.assertRaises(ValueError):client.decode_response(b'['*4000+b']'*4000,'a'*32,1)
    def test_paths_cannot_select_an_external_python_or_model(self):
        manifest=self.ready();client.inspect_runtime(self.home,manifest)
        python=self.home/manifest['python'];python.unlink();python.symlink_to(sys.executable)
        with self.assertRaises(ValueError):client.inspect_runtime(self.home,manifest)
        with self.assertRaises(ValueError):client.inspect_runtime(self.home,{**manifest,'python':'../python'})
    def test_missing_runtime_and_bad_requests_do_not_create_state(self):
        for texts in [[],[''],['x'*2001],['x']*17,[True]]:self.assertIsNone(client.encode(self.home,texts))
        self.assertIsNone(client.encode(self.home,['fictional query']));self.assertEqual(list(self.home.iterdir()),[])
    def test_failed_generation_cools_down_without_saving_query_text(self):
        manifest=self.ready()
        with patch.object(client,'_exchange',return_value=None)as exchange:
            self.assertIsNone(client.encode(self.home,['fictional private query']))
            self.assertIsNone(client.encode(self.home,['another fictional query']))
            self.assertEqual(exchange.call_count,1)
        self.assertNotIn('query',(self.home/'cooldown.json').read_text())
        manifest['recipe']='different-generation';(self.home/'active.json').write_text(json.dumps(manifest))
        def respond(_,payload,__):
            request=json.loads(payload);return json.dumps(self.response(request['id'],len(request['texts']))).encode()
        with patch.object(client,'_exchange',side_effect=respond):self.assertIsNotNone(client.encode(self.home,['fictional query']))
    def test_busy_encoder_does_not_wait_for_another_process_lock(self):
        self.ready()
        with (self.home/'query.lock').open('a')as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with patch.object(client,'_exchange')as exchange:self.assertIsNone(client.encode(self.home,['fictional query']));exchange.assert_not_called()
    def test_lock_symlink_cannot_change_permissions_on_an_unrelated_file(self):
        self.ready();other=self.home/'unrelated';other.write_text('fixture');other.chmod(0o644)
        (self.home/'query.lock').symlink_to(other)
        self.assertIsNone(client.encode(self.home,['fictional query']));self.assertEqual(other.stat().st_mode&0o777,0o644)
    def test_installer_refuses_external_runtime_subdirectories_before_downloads(self):
        other=tempfile.TemporaryDirectory();self.addCleanup(other.cleanup)
        (self.home/'models').symlink_to(other.name,target_is_directory=True)
        with patch.object(setup.subprocess,'run')as run:
            with self.assertRaises(ValueError):setup.install(self.home,Path('/fiction/uv'))
            run.assert_not_called()
    def test_bad_worker_request_fails_without_echoing_its_contents(self):
        result=subprocess.run([sys.executable,'-I',str(client.WORKER),str(self.home)],input=b'{"private_fixture":"do-not-echo-this"}',capture_output=True)
        self.assertEqual(result.returncode,1);self.assertNotIn(b'do-not-echo-this',result.stdout);self.assertEqual(result.stderr,b'')
    def test_failed_install_preserves_the_previous_active_generation(self):
        old=b'{"protocol":1,"recipe":"previous"}';(self.home/'active.json').write_bytes(old)
        with patch.object(setup,'model_files'),patch.object(setup.subprocess,'run'),patch.object(setup,'health',return_value=False):
            with self.assertRaises(ValueError):setup.install(self.home,Path('/fiction/uv'))
        self.assertEqual((self.home/'active.json').read_bytes(),old)
        self.assertEqual(list((self.home/'generations').iterdir()),[])
    def test_healthy_same_recipe_install_is_idempotent(self):
        recipe=hashlib.sha256(setup.LOCK.read_bytes()+setup.PYTHON_VERSION.encode()+client.MODEL_KEY.encode()).hexdigest()
        (self.home/'active.json').write_text(json.dumps({'recipe':recipe}))
        with patch.object(setup,'health',return_value=True),patch.object(setup,'model_files')as models,patch.object(setup.subprocess,'run')as run:
            self.assertFalse(setup.install(self.home,Path('/fiction/uv')));models.assert_not_called();run.assert_not_called()


if __name__=='__main__':unittest.main()

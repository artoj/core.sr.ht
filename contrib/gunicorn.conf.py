from prometheus_client import multiprocess
import shutil
import os

def on_starting(server):
    multiprocess_dir = os.environ["prometheus_multiproc_dir"]
    shutil.rmtree(multiprocess_dir)

def child_exit(server, worker):
    multiprocess.mark_process_dead(worker.pid)
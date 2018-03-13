'''
#################
# documentation #
#################

Version: 1

1. Dependencies:
    - python 3.
    - aiohttp package.

2. Make config file named ironr.json and set the path in IronConfig.config_file_name member.
    Example:
        {
            "worker" : {
                "projects" : [
                    {
                        "name" : "foo",
                        "project_id" : "...",
                        "project_token" : "..."
                    }
                ]
            }
        }

3. Set Task.host member to your iron.io host.

4. CLI usage: "ironr task regex" options:
    --name <name>
        Required. <name> must be in config, but can be anything you choose.
    --worker <name>
        Required. <name> must be a valid worker name.
    --search <string>
        Required. <string> must be either "logs" or "info". Only the payload is searched
        for "info".
    --max <int>
        Optional. <int> must be an integer between 1 and 100; defaults to 10. Determines
        how many pages are searched, where each page contains up to 100 tasks.
    --start <datetime>
        Optional. <datetime> format must be "%Y-%m-%d %H:%M:%S" or "now"; defaults to "now".
        Determines what time to start searching from. Example format: "2016-05-15 13:25:00".
    --regex <string>
        Required. <string> must be a python compatible regular expression.
    
    # assuming you made a "ironr" alias for "python3 /path/to/ironr.py". 
    ex) ironr task regex --name foo --worker my_worker --search logs --regex 'hello world'
'''

import sys
import signal
import json
from os.path import expanduser
import asyncio
from aiohttp import ClientSession
import re
import time
from collections import namedtuple

def ascii_table(rows):
    if len(rows) >= 1:
        headers = rows[0]._fields
        lens = []
        for i in range(len(rows[0])):
            lens.append(len(max([x[i] for x in rows] + [headers[i]], key=lambda x: len(str(x)))))
        formats = []
        hformats = []
        for i in range(len(rows[0])):
            if isinstance(rows[0][i], int):
                formats.append("%%%dd" % lens[i])
            else:
                formats.append("%%-%ds" % lens[i])
            hformats.append("%%-%ds" % lens[i])
        pattern = " | ".join(formats)
        hpattern = " | ".join(hformats)
        separator = "-+-".join(['-' * (n + 1) for n in lens])
        separator = "%s%s%s" % ('+', separator, '+',)
        print(separator)
        header = hpattern % headers
        header = "%s%s%s" % ('| ', header, ' |',)
        print(header)
        print(separator)
        for line in rows:
            line = pattern % tuple(line)
            line = "%s%s%s" % ('| ', line, ' |',)
            print(line)
            print(separator)

class IronException(Exception):
    
    def __init__(self, message):
        self.message = message
        
    def get_message(self):
        return 'Error: %s' % (self.message,)

class IronConfig():
    
    # change path to your choosing.
    config_file_name = '/usr/src/ironr.json'
    
    def __init__(self):
        try:
            self.config_path = IronConfig.config_file_name
            with open(self.config_path, 'r') as config_file:
                self.data = json.load(config_file)
        except Exception:
            raise IronException('unable to open config file at "%s".' % (self.config_path,))
    
    def get_by_name(self, service, name):
        try:
            (config,) = [config for config in self.data[service]['projects'] if config['name'] == name]
        except Exception:
            raise IronException('project "%s" not found in config file.' % (name,))
        return config
        
    def check_project_config(self, required_keys, config):
        missing_keys = list(required_keys - set(config.keys()))
        if (len(missing_keys) > 0):
            raise IronException('missing %s propertie(s) in project config.' % (', '.join(missing_keys),))
        else:
            return True

class Task():
    
    task_options = ('--project', '--worker', '--name',)
    required_project_keys = {'name', 'project_id', 'project_token'}
    
    # make sure this is your host.
    host = 'worker-aws-us-east-1'
    api_version = '2'
    
    def __init__(self, args):
        self.name = self.collect_option_value(Task.task_options[2], args, True)
        self.worker = self.collect_option_value(Task.task_options[1], args, True)
        iron_config = IronConfig()
        self.config = iron_config.get_by_name('worker', self.name)
        iron_config.check_project_config(Task.required_project_keys, self.config)
        self.project = self.config['project_id']
        
    def collect_option_value(self, token, args, required):
        try:
            if token in args:
                value = args[args.index(token) + 1]
                if value in self.get_sub_task_options():
                    raise Exception()
            elif not required:
                value = False
            else:
                 raise Exception()
        except Exception:
            raise IronException('missing or invalid %s option.' % (token,))
        return value
        
    def build_base_url(self):
        url = 'https://{host}.iron.io/{api_version}/projects/{project}/'.format(host=Task.host, api_version=Task.api_version, project=self.project)
        return url
        
class TaskRegex(Task):
    
    regex_options = ('--search', '--start', '--regex', '--max',)
    log_url = 'https://hud-e.iron.io/worker/projects/{project_id}/tasks/{task_id}/log'
    info_url = 'https://hud-e.iron.io/worker/projects/{project_id}/tasks/{task_id}'
    
    def __init__(self, args):
        Task.__init__(self, args)
        self.search = self.collect_option_value(TaskRegex.regex_options[0], args, True)
        start = self.collect_option_value(TaskRegex.regex_options[1], args, False)
        if start:
            self.start = self.get_start_time(start)
        else:
            self.start = self.get_start_time('now')
        regex = self.collect_option_value(TaskRegex.regex_options[2], args, True)
        max_pages = self.collect_option_value(TaskRegex.regex_options[3], args, False)
        if max_pages:
            self.max_pages = int(max_pages)
        else:
            self.max_pages = 10
        self.regex = re.compile(regex)
        self.base_url = self.build_base_url()
        self.loop = None
        self.session = None
        
    def get_sub_task_options(self):
        return TaskRegex.regex_options
        
    def get_start_time(self, start):
        if start == 'now':
            start = int(time.time())
        else:
            pattern = '%Y-%m-%d %H:%M:%S'
            start = int(time.mktime(time.strptime(start, pattern)))
        return start 
        
    def build_list_tasks_url(self, page):
        parts = {'base' : self.base_url, 'oauth' : self.config['project_token'], 'page' : page, 'results' : 100, 'worker' : self.worker, 'time' : self.start}
        url = '{base}tasks?oauth={oauth}&page={page}&per_page={results}&code_name={worker}&complete=1&to_time={time}'.format(**parts)
        return url
        
    def build_task_log_url(self, task_id):
        parts = {'base' : self.base_url, 'task_id' : task_id, 'oauth' : self.config['project_token']}
        url = '{base}tasks/{task_id}/log?oauth={oauth}'.format(**parts)
        return url
        
    def build_task_info_url(self, task_id):
        parts = {'base' : self.base_url, 'task_id' : task_id, 'oauth' : self.config['project_token']}
        url = '{base}tasks/{task_id}?oauth={oauth}'.format(**parts)
        return url
    
    def run(self):
        
        async def fetch(loop, session, url):
            async with session.get(url) as response:
                return await response.text()
        
        async def bound_fetch(loop, session, sem, url):
            async with sem:
                return await fetch(loop, session, url)
        
        def search_log(log):
            response = False
            if (self.regex.search(log)):
                response = True
            return response
            
        def search_payload(info):
            response = False
            info = json.loads(info)
            if (self.regex.search(info['payload'])):
                response = True
            return response
            
        def search_log_callback(task_matches, task):
            return lambda promise_log: task_matches.append(task) if search_log(promise_log.result()) else False
            
        def search_info_callback(task_matches, task):
            return lambda promise_info : task_matches.append(task) if search_payload(promise_info.result()) else False
            
        def build_task_info_request(loop, session, sem, tasks, task_matches):
            promises = []
            for task in tasks:
                task_info_url = self.build_task_info_url(task['id'])
                promise = asyncio.ensure_future(bound_fetch(loop, session, sem, task_info_url))
                promise.add_done_callback(search_info_callback(task_matches, task))
                promises.append(promise)
            return promises
            
        def build_task_log_request(loop, session, sem, tasks, task_matches):
            promises = []
            for task in tasks:
                task_log_url = self.build_task_log_url(task['id'])
                promise = asyncio.ensure_future(bound_fetch(loop, session, sem, task_log_url))
                promise.add_done_callback(search_log_callback(task_matches, task))
                promises.append(promise)
            return promises    
        
        async def build_list_tasks_requests(loop, session, sem, func, task_matches, list_tasks_url):
            response = await bound_fetch(loop, session, sem, list_tasks_url)
            response = json.loads(response)
            return func(loop, session, sem, response['tasks'], task_matches)
            
        async def build_task_pages(loop, session, func, task_matches):
            promises = []
            sem = asyncio.Semaphore(25)
            for page in range(self.max_pages):
                list_tasks_url = self.build_list_tasks_url(page)
                promises.append(asyncio.ensure_future(build_list_tasks_requests(loop, session, sem, func, task_matches, list_tasks_url)))
            promise_pages = await asyncio.gather(*promises)
            promise_requests = []
            [promise_requests.extend(promise_page) for promise_page in promise_pages]
            print('control-c to quit: processing %s logs...' % (len(promise_requests),))
            await asyncio.gather(*promise_requests)
        
        def print_results(task_matches, url):
            rows = []
            Row = namedtuple('Row', ['time', 'link'])
            for task in task_matches:
                task_link = url.format(project_id=self.project, task_id=task['id'])
                task_time = task['end_time']
                rows.append(Row(task_time, task_link))
            rows = sorted(rows, key=lambda row: row[0])
            if len(rows) > 0:
                ascii_table(rows)
            else:
                print('No matches found.')
        
        def signal_handler(future, task_matches, url):
            if self.loop and self.loop.is_running():
                future.cancel()
                self.loop.stop()
                print('Process terminated.')
                print_results(task_matches, url)
        
        start_time = time.time()
        
        task_matches = []
        loop = asyncio.get_event_loop()
        self.loop = loop
        session = ClientSession(loop=loop)
        self.session = session
        func = build_task_log_request if self.search == 'logs' else build_task_info_request
        url = self.log_url if self.search == 'logs' else self.info_url
        # must wait for this gather to finish before cancelling because parent Task won't exist otherwise.
        future = asyncio.gather(build_task_pages(loop, session, func, task_matches))
        loop.add_signal_handler(signal.SIGINT, lambda: signal_handler(future, task_matches, url))
        loop.run_until_complete(future)
        
        print_results(task_matches, url)
        
        end_time = time.time()
        print('Finished: %s secs.' % (round(end_time - start_time, 2),))
    
    def finish(self):
        if (self.session and not self.session.closed):
            self.session.close()
        if (self.loop and not self.loop.is_closed()):
            self.loop.close()
        sys.exit(0)

def route_command(args):
    argv_count = len(args)
    if argv_count >= 3:
        if args[1] in command_tokens:
            if args[2] in commands[args[1]]:
                return commands[args[1]][args[2]](args)
            else:
                raise IronException('subcommand "%s" does not exist.' % (args[2],))
                
        else:
            raise IronException('command "%s" does not exist.' % (args[1],))
    else:
        raise IronException('no command and/or subcommand given.')

command_tokens = ('task',)
commands = {'task' : {'regex' : TaskRegex}}

try:
    command = None
    command = route_command(list(sys.argv))
    command.run()
except IronException as e:
    print(e.get_message())
finally:
    if (command):
        command.finish()
        
# ironr
A small Python 3 CLI to search iron.io task logs.

1. Dependencies:
    - python 3.
    - aiohttp package.

2. Make config file named `ironr.json` and set the path in `IronConfig.config_file_name` member.
    Example:
    `
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
    `

3. Set `Task.host` member to your iron.io host.

4. CLI usage: "ironr task regex" options:
    * --name <name>
        Required. <name> must be in config, but can be anything you choose.
    * --worker <name>
        Required. <name> must be a valid worker name.
    * --search <string>
        Required. <string> must be either "logs" or "info". Only the payload is searched
        for "info".
    * --max <int>
        Optional. <int> must be an integer between 1 and 100; defaults to 10. Determines
        how many pages are searched, where each page contains up to 100 tasks.
    * --start <datetime>
        Optional. <datetime> format must be "%Y-%m-%d %H:%M:%S" or "now"; defaults to "now".
        Determines what time to start searching from. Example format: "2016-05-15 13:25:00".
    * --regex <string>
        Required. <string> must be a python compatible regular expression.
    
    Assuming you made a "ironr" alias for "python3 /path/to/ironr.py". 
    ex) `ironr task regex --name foo --worker my_worker --search logs --regex 'hello world'`

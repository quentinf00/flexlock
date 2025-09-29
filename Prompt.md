improvements:

- the commit_cwd function shoulc have a 'filesize_warn' argument defaulting to 1Mb that trigger a warning if the function is about to commit a file bigger than that.
- The runlock function should have a commit argument defualting to True, which make the runlock create fresh commits for the repo to capture the actual state of the repo

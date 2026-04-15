# Pushing changes to GitHub

After you edit files in this project:

```bash
cd ~/netpulse-project
git status
git add .
git commit -m "Describe your change in one line"
git push
```

`main` already tracks `origin/main`, so you usually only need **`git push`** (no `-u origin main`).

If Git asks for credentials over HTTPS:

- **Username:** your GitHub username  
- **Password:** your **Personal Access Token** (not your GitHub account password)

To save credentials so you are not prompted every time:

```bash
git config --global credential.helper store
```

(Run once; the next successful login is stored in `~/.git-credentials` — keep that file private.)

If the push is rejected because the remote has new commits:

```bash
git pull --rebase origin main
git push
```

# Create (or reuse) a temporary worktree for gh-pages
GHWT=$HOME/tmp/$(basename $(pwd))-gh-pages
git worktree add $GHWT gh-pages || git worktree add -B gh-pages $GHWT origin/gh-pages

# Copy your build output into it
rclone copy docs/_build/ $GHWT/ -P

touch $GHWT/.nojekyll
# Commit and push
cd $GHWT
git add --all
git commit -m "Update docs" || echo "No changes to commit"
git push origin gh-pages

# Clean up
cd -
git worktree remove $GHWT

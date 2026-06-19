#!/bin/bash

SPOTLIGHT_JID=$(sbatch --parsable spotlight/serve.job)
SMALL_JID=$(sbatch --parsable vllm/serve_small.job)
BIG_JID=$(sbatch --parsable vllm/serve_big.job)

echo "Submitted: spotlight=$SPOTLIGHT_JID  small=$SMALL_JID  big=$BIG_JID"
echo "Waiting for all jobs to start..."

get_node() {
    squeue -j $1 -h -o "%T %N" 2>/dev/null | awk '$1 == "RUNNING" {print $2}'
}

while true; do
    SPOTLIGHT_NODE=$(get_node $SPOTLIGHT_JID)
    SMALL_NODE=$(get_node $SMALL_JID)
    BIG_NODE=$(get_node $BIG_JID)

    [ -n "$SPOTLIGHT_NODE" ] && [ -n "$SMALL_NODE" ] && [ -n "$BIG_NODE" ] && break

    sleep 10
done

echo ""
echo "All jobs running. SSH tunnel:"
echo ""
echo "  ssh -N \\"
echo "    -L 2223:${SPOTLIGHT_NODE}:2223 \\"
echo "    -L 8267:${SMALL_NODE}:8267 \\"
echo "    -L 8268:${BIG_NODE}:8268 \\"
echo "    ${USER}@snellius.surf.nl"
echo ""

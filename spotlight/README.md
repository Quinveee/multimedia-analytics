# DBpedia Spotlight on Snellius

Submit from repo root (`~/multimedia-analytics`).

## 1. Install (first time only)

```bash
sbatch spotlight/install.job
```

## 2. Serve

```bash
sbatch spotlight/serve.job
```

Check the node: `squeue -u $USER`

## 3. SSH tunnel (local machine)

```bash
ssh -N -L 2223:<node>:2223 scur0267@snellius.surf.nl
```

## 4. Test

```bash
curl http://localhost:2223/rest/annotate \
  --data-urlencode "text=Marie Curie was a Polish physicist." \
  --data "confidence=0.35" \
  -H "Accept: application/json"
```

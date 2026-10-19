import { defineRailway, github, postgres, project, redis, service, volume } from "railway/iac";

export default defineRailway(() => {
  const bitunixTrader = github("marcrr79907/bitunix-trader", { branch: "develop", checkSuites: false });

  const Redis = redis("Redis", { region: "iad" });
  Redis.deploy = { startCommand: "/bin/sh -c \"rm -rf $RAILWAY_VOLUME_MOUNT_PATH/lost+found/ && exec docker-entrypoint.sh redis-server --requirepass $REDIS_PASSWORD --save 60 1 --dir $RAILWAY_VOLUME_MOUNT_PATH\"" };
  Redis.networking = { privateNetworkEndpoint: "redis" };
  const Postgres = postgres("Postgres", { region: "iad" });
  Postgres.networking = { privateNetworkEndpoint: "postgres" };
  const redisVolume = volume("redis-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "iad", sizeMB: 500 });
  const postgresVolume = volume("postgres-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "iad", sizeMB: 500 });
  const worker = service("worker", {
    source: bitunixTrader,
    start: "python web/worker.py",
    replicas: { "iad": 1 },
  });
  const scheduler = service("scheduler", {
    source: bitunixTrader,
    start: "python web/manage.py prune_snapshots --older-than 7",
    replicas: { "iad": 1 },
    deploy: { cronSchedule: "0 3 * * *", restartPolicyType: "NEVER" },
  });
  const web = service("web", {
    source: bitunixTrader,
    start: "sh web/start.sh",
    healthcheck: "/healthz",
    healthcheckTimeout: 60,
    preDeploy: "python web/manage.py migrate --noinput",
    replicas: { "iad": 1 },
  });

  return project("joyful-enthusiasm", {
    variables: { managed: false },
    resources: [Redis, Postgres, worker, scheduler, web, redisVolume, postgresVolume],
  });
});

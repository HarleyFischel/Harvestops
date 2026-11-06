# Portal-to-app token exchange sample

`harvestops.token_exchange.PortalTokenExchange` is an isolated trust-model demonstration. It issues short-lived RS256 JWTs with `iss`, `aud`, `iat`, `nbf`, `exp`, `jti`, and `kid`, then consumes each `jti` once through a replay store. It is not an implementation of Pero Central.

The exchange should happen through a back-channel or authenticated POST, not by placing a long-lived bearer token in a URL. The receiving service must validate the explicit RS256 algorithm, issuer, audience, time claims, subject, and key identifier before creating its own short-lived session.

Key rotation: publish a new public key under a new `kid`, accept both old and new kids during the overlap window, switch issuers to the new key, then retire the old key after all short-lived tokens have expired. Store private keys in a managed secret store and keep replay state shared across replicas. `RedisReplayStore` provides the shared option with an atomic Redis `SET NX` and token TTL:

```python
from redis import Redis
from harvestops.token_exchange import PortalTokenExchange, RedisReplayStore

replay = RedisReplayStore(Redis.from_url("redis://localhost:6379/0"))
exchange = PortalTokenExchange(private_key, public_key, issuer, audience, replay=replay)
```

The default in-memory store is retained only for isolated local tests. Redis connectivity and production key distribution are not verified in this environment.

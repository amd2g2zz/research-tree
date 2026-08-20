## Design

Legacy single-track strategies receive one deterministic default track to keep
old handoffs usable. Explicit multi-track strategies are fail-closed: each
active track must cover at least one current research question, and a
multi-track question must name a valid `track_id`.

Native dependencies are retained as scheduling edges only after a structured
edge proves either an exact producer artifact relation or a confirmed authority
constraint. Status and delivery snapshots report the ready wave, ready tracks,
and every blocked dependency with its justification.

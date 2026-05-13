# Attach-First Demo

1. Start `COMSOL Multiphysics Server` manually.
2. Note the real listening port shown by the server console.
3. Open COMSOL Desktop and connect to that same port.
4. Import or switch to the server-side model in Desktop.
5. From MCP, run:

```text
server_connect("localhost", <actual_port>)
model_create("VisibleServerModel")
ensure_component("comp1", 2)
ensure_geometry("comp1", "geom1", 2)
ensure_mesh("comp1", "mesh1")
create_feature("comp1", "geom1", "r1", "Rectangle", "[{\"name\":\"size\",\"values\":[\"60[mm]\",\"30[mm]\"]},{\"name\":\"pos\",\"values\":[\"-30[mm]\",\"-15[mm]\"]}]", true)
run_feature("mesh", "mesh1", "comp1")
```

You should see the same model update in COMSOL Desktop because Desktop and MCP
share the same server-side model.

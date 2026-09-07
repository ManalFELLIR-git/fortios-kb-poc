from kb_builder.terraform_extractor import parse_schema_entry

tests = {

    "string_choices": r'''
        Type: schema.TypeString,
        Optional: true,
        ValidateFunc: validation.StringInSlice(
            []string{"enable", "disable"},
            false,
        ),
    ''',

    "integer_choices": r'''
        Type: schema.TypeInt,
        Optional: true,
        ValidateFunc: validation.IntInSlice(
            []int{0, 1, 2},
        ),
    ''',

    "default_string": r'''
        Type: schema.TypeString,
        Optional: true,
        Default: "disable",
    ''',

    "default_integer": r'''
        Type: schema.TypeInt,
        Optional: true,
        Default: 60,
    ''',

    "range": r'''
        Type: schema.TypeInt,
        Optional: true,
        ValidateFunc: validation.IntBetween(2, 4),
    ''',

    "parent_child_protection": r'''
        Type: schema.TypeList,
        Optional: true,
        Elem: &schema.Resource{
            Schema: map[string]*schema.Schema{
                "child": &schema.Schema{
                    Type: schema.TypeInt,
                    Optional: true,
                    ValidateFunc: validation.IntBetween(100, 200),
                },
            },
        },
    ''',
}


for name, body in tests.items():

    print()
    print(
        "=" * 60
    )

    print(name)

    print(
        parse_schema_entry(body)
    )

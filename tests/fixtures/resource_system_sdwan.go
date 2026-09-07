package fortios
func resourceSystemSdwan() *schema.Resource {
 return &schema.Resource{Schema: map[string]*schema.Schema{
  "status": &schema.Schema{Type: schema.TypeString, Optional: true, Computed: true},
  "duplication_max_num": &schema.Schema{Type: schema.TypeInt, ValidateFunc: validation.IntBetween(2, 4), Optional: true},
  "members": &schema.Schema{Type: schema.TypeList, Optional: true, Elem: &schema.Resource{Schema: map[string]*schema.Schema{
    "interface": &schema.Schema{Type: schema.TypeString, ValidateFunc: validation.StringLenBetween(0, 15), Optional: true},
  }}},
 }}
}

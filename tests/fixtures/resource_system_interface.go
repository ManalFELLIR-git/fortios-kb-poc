package fortios

func resourceSystemInterface() *schema.Resource {
 return &schema.Resource{Schema: map[string]*schema.Schema{
  "name": &schema.Schema{Type: schema.TypeString, Optional: true},
 }}
}

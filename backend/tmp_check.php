<?php
require "vendor/autoload.php";
$f = new Database\Factories\UserFactory;
$r = new ReflectionObject($f);
$p = $r->getProperty("faker");
$p->setAccessible(true);
$val = $p->getValue($f);
var_dump($val instanceof Faker\Generator);
var_dump(get_class($val));

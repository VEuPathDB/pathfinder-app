#!groovy

@Library('pipelib')
import org.veupathdb.lib.Builder

node('podbuild') {
  def builder = new Builder(this)

  builder.gitClone()
  builder.buildContainers([
    [ name: 'pathfinder-api', dockerfile: 'apps/api/Dockerfile' ],
    [ name: 'pathfinder-web', dockerfile: 'apps/web/Dockerfile',
      buildArgs: [ NEXT_PUBLIC_API_URL: 'http://pathfinder-api:8000' ] ]
  ])
}
